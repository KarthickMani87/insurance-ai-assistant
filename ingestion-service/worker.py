import os
import time
import boto3
import docx2txt
import pdfplumber
import json
import pika
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET = os.getenv("S3_BUCKET")
QUEUE_NAME = os.getenv("QUEUE_NAME", "documents")

s3_client = boto3.client("s3", region_name=AWS_REGION)

# 🔄 Retry wrapper for RabbitMQ connection
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


def extract_text_from_file(local_path: str):
    if local_path.endswith(".pdf"):
        text = ""
        with pdfplumber.open(local_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
        return text

    elif local_path.endswith(".docx"):
        return docx2txt.process(local_path)

    else:
        raise ValueError("Unsupported file type")


def process_file(key: str):
    local_path = f"/tmp/{os.path.basename(key)}"
    s3_client.download_file(S3_BUCKET, key, local_path)

    text = extract_text_from_file(local_path)

    payload = {
        "key": key,
        "filename": os.path.basename(key),
        "bucket": S3_BUCKET,
        "text": text,
    }

    # Publish message to RabbitMQ
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)  # persistent
    )
    print(f"📤 Sent {key} to RabbitMQ for embedding")


def poll_s3():
    """ Simple polling loop — replace with S3 event-driven triggers in production """
    seen = set()
    while True:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="uploads/")
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key not in seen:
                print(f"🔍 New file detected: {key}")
                try:
                    process_file(key)
                    seen.add(key)
                except Exception as e:
                    print(f"❌ Failed to process {key}: {e}")
        time.sleep(30)


if __name__ == "__main__":
    print("🚀 Ingestion worker started, watching S3...")
    poll_s3()
