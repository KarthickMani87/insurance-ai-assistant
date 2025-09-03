import os
import requests
import json
import time
import pika
import redis
from chromadb import HttpClient
from huggingface_hub import login
from dotenv import load_dotenv

# --- Load env ---
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

print(f"🔗 Using embeddings model: {EMBED_MODEL}")

# --- Globals ---
_embedding_dim_cache = None
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 32))

_batch = {"ids": [], "embeddings": [], "documents": [], "metadatas": []}

# --- Helpers ---
def sanitize_metadata(meta: dict) -> dict:
    clean = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            clean[k] = v
        else:
            clean[k] = str(v)
    return clean


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


def embed_text(text: str):
    global _embedding_dim_cache

    text = (text or "").strip()
    if not text:
        print("⚠️ Skipping empty text embedding")
        return [0.0] * (_embedding_dim_cache or 384)

    payload = {"model": EMBED_MODEL, "input": text}
    resp = requests.post(EMBEDDINGS_URL, json=payload, timeout=30)
    resp.raise_for_status()

    vector = resp.json()["data"][0]["embedding"]

    # Detect embedding size once
    if _embedding_dim_cache is None:
        _embedding_dim_cache = len(vector)
        print(f"📐 Detected embedding size: {_embedding_dim_cache}")

    return vector


def flush_batch():
    if not _batch["ids"]:
        return
    try:
        collection.add(
            ids=_batch["ids"],
            embeddings=_batch["embeddings"],
            documents=_batch["documents"],
            metadatas=_batch["metadatas"],
        )
        print(f"✅ Flushed {len(_batch['ids'])} chunks to vector DB")
    except Exception as e:
        print(f"❌ Failed batch insert: {e}")
    finally:
        for k in _batch:
            _batch[k].clear()


def process_message(ch, method, properties, body):
    msg = json.loads(body)
    key = msg["key"]
    filename = msg["filename"]
    chunk_id = msg["chunk_id"]
    total_chunks = msg["total_chunks"]
    text = msg["text"]

    print(f"🧩 Embedding {filename} [chunk {chunk_id+1}/{total_chunks}]")

    try:
        vector = embed_text(text)

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
            "section": msg.get("section", "GENERAL"),
        }

        metadata = sanitize_metadata(metadata)

        # Batch insert
        _batch["ids"].append(doc_id)
        _batch["embeddings"].append(vector)
        _batch["documents"].append(text)
        _batch["metadatas"].append(metadata)

        if len(_batch["ids"]) >= BATCH_SIZE:
            flush_batch()

        job_id = os.path.basename(key)
        update_progress(job_id, total_chunks)

    except Exception as e:
        print(f"❌ Failed embedding {filename} chunk {chunk_id}: {e}")

    ch.basic_ack(delivery_tag=method.delivery_tag)


def consume():
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, heartbeat=60)
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
    try:
        consume()
    finally:
        flush_batch()
