import os
import time
import boto3
import docx2txt
import pdfplumber
import json
import pika
import re
from dotenv import load_dotenv
from transformers import AutoTokenizer
from botocore.client import Config

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET = os.getenv("S3_BUCKET")
QUEUE_NAME = os.getenv("QUEUE_NAME", "documents")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=AWS_REGION,
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
)

# --- RabbitMQ Connect ---
def connect_rabbitmq(max_retries=10, delay=5):
    for attempt in range(max_retries):
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host="rabbitmq", heartbeat=600)
            )
            print("✅ Connected to RabbitMQ")
            return connection
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ RabbitMQ not ready, retrying in {delay}s... (attempt {attempt+1}/{max_retries})")
            time.sleep(delay)
    raise Exception("❌ Could not connect to RabbitMQ after retries")

connection = connect_rabbitmq()
channel = connection.channel()
channel.queue_declare(queue=QUEUE_NAME, durable=True)

# --- Load Tokenizer for embeddings ---
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
MAX_TOKENS = 512
MIN_TOKENS = 100

def tokenize_length(text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))

# --- Dynamic Chunking ---
def detect_blocks(text: str):
    """Split into semantic blocks: paragraphs, lists, tables"""
    lines = text.split("\n")
    blocks, buffer = [], []

    def flush():
        nonlocal buffer
        if buffer:
            blocks.append("\n".join(buffer).strip())
            buffer = []

    for line in lines:
        line_strip = line.strip()

        # Table
        if "|" in line_strip or "\t" in line_strip:
            flush()
            blocks.append(line_strip)
            continue

        # Bullet list
        if re.match(r"^(\*|-|•)\s+", line_strip):
            buffer.append(line_strip)
            continue

        # Numbered list
        if re.match(r"^\d+\.\s+", line_strip):
            buffer.append(line_strip)
            continue

        # Paragraph break
        if line_strip == "":
            flush()
        else:
            buffer.append(line_strip)

    flush()
    return blocks

def dynamic_chunk(text: str):
    chunks = []
    blocks = detect_blocks(text)

    buffer, buffer_tokens = [], 0
    for block in blocks:
        tokens = tokenize_length(block)

        if tokens < MAX_TOKENS:
            if buffer_tokens + tokens < MAX_TOKENS:
                buffer.append(block)
                buffer_tokens += tokens
            else:
                chunks.append("\n\n".join(buffer))
                buffer = [block]
                buffer_tokens = tokens
        else:
            # Split large block
            words, sub_chunk, sub_tokens = block.split(), [], 0
            for word in words:
                word_tokens = tokenize_length(word)
                if sub_tokens + word_tokens > MAX_TOKENS:
                    chunks.append(" ".join(sub_chunk))
                    sub_chunk, sub_tokens = [word], word_tokens
                else:
                    sub_chunk.append(word)
                    sub_tokens += word_tokens
            if sub_chunk:
                chunks.append(" ".join(sub_chunk))

    if buffer:
        chunks.append("\n\n".join(buffer))

    # Merge very small chunks
    final_chunks = []
    for chunk in chunks:
        if final_chunks and tokenize_length(chunk) < MIN_TOKENS:
            merged = final_chunks.pop() + "\n\n" + chunk
            if tokenize_length(merged) <= MAX_TOKENS:
                final_chunks.append(merged)
            else:
                final_chunks.extend([chunk])
        else:
            final_chunks.append(chunk)

    return final_chunks

# --- File Processing ---
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
    chunks = dynamic_chunk(text)

    for i, chunk in enumerate(chunks):
        payload = {
            "key": key,
            "filename": os.path.basename(key),
            "bucket": S3_BUCKET,
            "chunk_id": i,
            "total_chunks": len(chunks),
            "text": chunk,
        }
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2)
        )
    print(f"📤 Sent {len(chunks)} chunks for {key} to RabbitMQ")

def poll_s3():
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
