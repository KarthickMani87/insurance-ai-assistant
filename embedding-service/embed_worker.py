import os
import json
import pika
import requests
import time
from chromadb import HttpClient

# --- Env vars ---
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
QUEUE_NAME = os.getenv("QUEUE_NAME", "documents")
VECTOR_DB_HOST = os.getenv("VECTOR_DB_HOST", "http://vector-db:8000")
EMBED_MODEL = os.getenv("EMBED_MODEL", "mxbai-embed-large")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/embeddings")

# --- Connect to Chroma ---
chroma_client = HttpClient(host="vector-db", port=8000)
collection = chroma_client.get_or_create_collection(name="documents")

# --- Call Ollama embeddings ---
def embed_text(text: str):
    """Call Ollama to embed text"""
    response = requests.post(
        OLLAMA_URL,
        json={"model": EMBED_MODEL, "input": text}
    )
    response.raise_for_status()
    data = response.json()

    # Handle both single and batch embedding cases
    vector = data.get("embedding") or []
    if not vector or len(vector) == 0:
        raise ValueError(f"Got empty embedding from Ollama for input length={len(text)}")

    return vector

# --- Process each message ---
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
        print(f"   → Embedding length: {len(vector)}")

        doc_id = f"{key}__{chunk_id}"  # unique per chunk
        metadata = {
            "filename": filename,
            "key": key,
            "chunk_id": chunk_id,
            "total_chunks": total_chunks,
        }

        # Ensure embeddings is 2D list
        collection.add(
            ids=[doc_id],
            embeddings=[vector],  # wrapped in list
            documents=[text],
            metadatas=[metadata],
        )

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

def wait_for_model():
    import time
    while True:
        try:
            r = requests.post(
                OLLAMA_URL,
                json={"model": EMBED_MODEL, "input": "ping"}
            )
            data = r.json()
            if data.get("embedding") and len(data["embedding"]) > 0:
                print(f"✅ Model {EMBED_MODEL} is ready with embedding size {len(data['embedding'])}")
                return
        except Exception as e:
            print(f"⏳ Waiting for Ollama model {EMBED_MODEL}... {e}")
        time.sleep(3)

if __name__ == "__main__":
    wait_for_model()
    consume()
