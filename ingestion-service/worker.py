import os
import time
import json
import re
import redis
import boto3
import docx2txt
import pdfplumber
import pika
from dotenv import load_dotenv
from transformers import AutoTokenizer
from botocore.client import Config

# --- Load env variables ---
load_dotenv()

# --- AWS ---
AWS_REGION = os.getenv("AWS_REGION")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET = os.getenv("S3_BUCKET")

# --- RabbitMQ ---
QUEUE_NAME = os.getenv("QUEUE_NAME", "documents")

# --- Redis ---
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# --- S3 Client ---
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
)

def create_job(job_id, filename, total_chunks):
    job = {
        "job_id": job_id,
        "filename": filename,
        "status": "pending",
        "total_chunks": total_chunks,
        "chunks_done": 0,
        "created_at": time.time(),
    }
    r.hset(f"job:{job_id}", mapping=job)
    r.expire(f"job:{job_id}", 60 * 60 * 24 * 7)

def mark_processing(job_id):
    r.hset(f"job:{job_id}", "status", "processing")
    r.hset(f"job:{job_id}", "updated_at", time.time())

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
MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
MAX_TOKENS = int(os.getenv("MAX_TOKENS", 384))  # MiniLM default = 384
MIN_TOKENS = int(os.getenv("MIN_TOKENS", 5))

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

        if "|" in line_strip or "\t" in line_strip:
            flush()
            blocks.append(line_strip)
            continue

        if re.match(r"^(\*|-|•)\s+", line_strip):  # bullets
            buffer.append(line_strip)
            continue

        if re.match(r"^\d+\.\s+", line_strip):  # numbered list
            buffer.append(line_strip)
            continue

        if line_strip == "":  # paragraph break
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

        # 🚨 Block itself too long
        if tokens > MAX_TOKENS:
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
            continue

        # Normal accumulation
        if buffer_tokens + tokens <= MAX_TOKENS:
            buffer.append(block)
            buffer_tokens += tokens
        else:
            chunks.append("\n\n".join(buffer))
            buffer, buffer_tokens = [block], tokens

    if buffer:
        chunks.append("\n\n".join(buffer))

    # --- Final safeguard: enforce string + truncate ---
    final_chunks = []
    for chunk in chunks:
        if not isinstance(chunk, str):
            chunk = " ".join(map(str, chunk))  # flatten list → string
        tokens = tokenizer.encode(chunk, add_special_tokens=False)
        if len(tokens) > MAX_TOKENS:
            tokens = tokens[:MAX_TOKENS]
            chunk = tokenizer.decode(tokens)
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

    job_id = os.path.basename(key)

    # Step 1: Create job
    create_job(job_id=key, filename=os.path.basename(key), total_chunks=len(chunks))
    mark_processing(key)

    # Step 2: Publish chunks
    for i, chunk in enumerate(chunks):
        if not isinstance(chunk, str):
            chunk = str(chunk)

        payload = {
            "key": key,
            "filename": os.path.basename(key),
            "bucket": S3_BUCKET,
            "chunk_id": i,
            "total_chunks": len(chunks),
            "text": chunk,   # always safe string
        }

        print(f"📤 Publishing chunk {i+1}/{len(chunks)} for {key}, length={len(chunk)} chars")
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2)
        )

    print(f"✅ Sent {len(chunks)} chunks for {key} to RabbitMQ")

def poll_s3():
    seen = set()
    print(f"📦 Watching bucket: {S3_BUCKET}/uploads/")
    while True:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix="uploads/")
        contents = response.get("Contents", [])
        print(f"🔎 Found {len(contents)} files in uploads/")

        for obj in contents:
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
