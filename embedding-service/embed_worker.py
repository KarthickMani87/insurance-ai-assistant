import os
import json
import time
import pika
import requests
import chromadb
from dotenv import load_dotenv

load_dotenv()

QUEUE_NAME = os.getenv("QUEUE_NAME", "documents")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/embeddings")
MODEL = os.getenv("EMBED_MODEL", "mxbai-embed-large")

# Retry wrapper for RabbitMQ connection
def connect_rabbitmq(max_retries=10, delay=5):
    for attempt in range(max_retries):
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host="rabbitmq")
            )
            print("✅ Connected to RabbitMQ")
            return connection
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ RabbitMQ not ready, retrying in {delay}s... (attempt {attempt+1}/{max_retries})")
            time.sleep(delay)
    raise Exception("❌ Could not connect to RabbitMQ after retries")

# Connect
connection = connect_rabbitmq()
channel = connection.channel()
channel.queue_declare(queue=QUEUE_NAME, durable=True)

# Chroma client
chroma_client = chromadb.HttpClient(host="vector-db", port=8000)
collection = chroma_client.get_or_create_collection("insurance_docs")


def generate_embedding(text: str):
    resp = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": text}
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def callback(ch, method, properties, body):
    msg = json.loads(body)
    print(f"📥 Received {msg['filename']} from RabbitMQ")

    embedding = generate_embedding(msg["text"])

    collection.add(
        ids=[msg["key"]],
        embeddings=[embedding],
        documents=[msg["text"]],
        metadatas=[{"filename": msg["filename"], "bucket": msg["bucket"]}]
    )

    print(f"✅ Stored embedding for {msg['filename']} in vector DB")

    ch.basic_ack(delivery_tag=method.delivery_tag)


if __name__ == "__main__":
    print("🚀 Embedding worker started, waiting for messages...")
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    channel.start_consuming()
