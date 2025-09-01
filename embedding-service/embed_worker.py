import os
import requests
import json
import time
import pika
import redis
from chromadb import HttpClient
from huggingface_hub import login
from pydantic import BaseModel
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv


# --- Load env file (useful for local dev; in Docker, envs are already injected) ---
load_dotenv()

# --- HuggingFace auth ---
hf_token = os.getenv("HF_TOKEN")
if hf_token:
    login(token=hf_token)

# --- Redis ---
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# --- RabbitMQ ---
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.getenv("RABBITMQ_DEFAULT_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_DEFAULT_PASS", "guest")
QUEUE_NAME = os.getenv("QUEUE_NAME", "documents")

# --- Vector DB ---
VECTOR_DB_HOST = os.getenv("VECTOR_DB_HOST", "vector-db")
VECTOR_DB_PORT = int(os.getenv("VECTOR_DB_PORT", 8000))
COLLECTION_NAME = os.getenv("VECTOR_COLLECTION", "insurance_docs")

chroma_client = HttpClient(host=VECTOR_DB_HOST, port=VECTOR_DB_PORT)
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

# --- Embeddings ---
EMBED_MODEL = os.getenv("EMBED_MODEL", "mixedbread-ai/mxbai-embed-large-v1")
EMBEDDINGS_URL = os.getenv("EMBEDDINGS_URL")

MODEL_VECTOR_SIZE = int(os.getenv("EMBED_VECTOR_SIZE", "384"))

print(f"🔗 Using OpenAIEmbeddings : {EMBED_MODEL}")


# --- Metadata sanitizer ---
def sanitize_metadata(meta: dict) -> dict:
    clean = {}
    for k, v in meta.items():
        if v is None:
            continue  # skip nulls
        if isinstance(v, (str, int, float, bool)):
            clean[k] = v
        else:
            clean[k] = str(v)  # force to string if weird type
    return clean


# --- Redis progress tracking ---
def update_progress(job_id, total_chunks):
    job_key = f"job:{job_id}"

    if not r.exists(job_key):
        print(f"⚠️ Redis job {job_key} not found — creating placeholder")
        r.hset(job_key, mapping={
            "status": "processing",
            "total_chunks": total_chunks,
            "chunks_done": 0,
            "created_at": time.time()
        })

    new_done = r.hincrby(job_key, "chunks_done", 1)
    r.hset(job_key, "updated_at", time.time())

    total = r.hget(job_key, "total_chunks")
    print(f"📊 Progress for {job_id}: {new_done}/{total}")

    if new_done >= int(total):
        r.hset(job_key, "status", "complete")
        print(f"✅ Job {job_id} marked complete in Redis")

# --- Call embedding model ---
def embed_text(text: str):
    text = (text or "").strip()  # handle None and whitespace
    if not text:
        print("⚠️ Skipping empty text embedding")
        # Return a zero-vector (same dimension every time) to keep downstream code happy
        return [0.0] * MODEL_VECTOR_SIZE   # <-- replace 768 with your model’s embedding size
    
    try:
        payload = {"model": EMBED_MODEL, "input": text}
        resp = requests.post(EMBEDDINGS_URL, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    except Exception as e:
        print(f"❌ Embedding failed for text: {str(text)[:50]}... | Error: {e}")
        raise


# --- Process each message ---
def process_message(ch, method, properties, body):
    msg = json.loads(body)
    key = msg["key"]
    filename = msg["filename"]
    chunk_id = msg["chunk_id"]
    total_chunks = msg["total_chunks"]
    text = msg["text"]

    print(f"🧩 Embedding {filename} [chunk {chunk_id+1}/{total_chunks}]")
    if not isinstance(text, str):
        print("❌ text is not a string! Example value:", str(text)[:200])

    try:
        vector = embed_text(text)
        print(f"   → Embedding length: {len(vector)}")

        doc_id = f"{key}__{chunk_id}"
        metadata = {
            "filename": filename,
            "key": key,
            "chunk_id": chunk_id,
            "total_chunks": total_chunks,
            "policyholder_name": msg.get("policyholder_name"),
            "policy_number": msg.get("policy_number"),
            "policy_type": msg.get("policy_type"),
            "coverage": msg.get("coverage"),
            "start_date": msg.get("start_date"),
            "end_date": msg.get("end_date"),
        }

        metadata = sanitize_metadata(metadata)

        collection.add(
            ids=[doc_id],
            embeddings=[vector],
            documents=[text],
            metadatas=[metadata],
        )
        update_progress(key, total_chunks)

        print(f"✅ Stored chunk {chunk_id+1}/{total_chunks} for {filename} in vector DB")

    except Exception as e:
        print(f"❌ Failed embedding {filename} chunk {chunk_id}: {e}")

    ch.basic_ack(delivery_tag=method.delivery_tag)


def consume():
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, heartbeat=600)
            )
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)

            print("🚀 Embedding worker started, waiting for messages...")
            channel.start_consuming()
        except Exception as e:
            print(f"⚠️ Embedding worker error: {e}, retrying in 5s...")
            time.sleep(5)


if __name__ == "__main__":
    print(f"EMBEDDING: Starting worker with model {EMBED_MODEL}")
    consume()
