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
from fastapi import FastAPI
import threading
from fastapi.middleware.cors import CORSMiddleware

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

# --- Job Tracking ---
def create_job(job_id, filename, total_chunks):
    print("JOB ID CREATED:", job_id)
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
                pika.ConnectionParameters(host="rabbitmq", heartbeat=60)
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

# --- Load Tokenizer ---
MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/all-mpnet-base-v2")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

MAX_TOKENS = int(os.getenv("MAX_TOKENS", 450))
MIN_TOKENS = int(os.getenv("MIN_TOKENS", 20))
OVERLAP = int(os.getenv("OVERLAP", 60))

def tokenize_length(text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))

# --- Section detection ---
SECTION_KEYWORDS = [
    "DEFINITIONS", "EXCLUSIONS", "COVERAGE", "WAITING PERIOD",
    "BENEFITS", "CLAIMS", "TERMS AND CONDITIONS"
]

def detect_section(line: str, current_section: str) -> str:
    upper_line = line.strip().upper()
    for keyword in SECTION_KEYWORDS:
        if keyword in upper_line:
            return keyword
    return current_section

# --- Block Detection ---
def detect_blocks(text: str):
    """Split into semantic blocks and tag sections."""
    lines = text.split("\n")
    blocks, buffer = [], []
    current_section = "GENERAL"

    def flush():
        nonlocal buffer, current_section
        if buffer:
            blocks.append({"text": "\n".join(buffer).strip(), "section": current_section})
            buffer = []

    for line in lines:
        current_section = detect_section(line, current_section)
        line_strip = line.strip()

        if "|" in line_strip or "\t" in line_strip:
            flush()
            blocks.append({"text": f"[TABLE START]\n{line_strip}\n[TABLE END]", "section": current_section})
            continue

        if re.match(r"^(\*|-|•)\s+", line_strip) or re.match(r"^\d+\.\s+", line_strip):
            buffer.append("[LIST ITEM] " + line_strip)
            continue

        if line_strip == "":
            flush()
        else:
            buffer.append(line_strip)

    flush()
    return blocks

# --- Chunking with Overlap ---
def dynamic_chunk(text: str, max_tokens=MAX_TOKENS, overlap=OVERLAP):
    blocks = detect_blocks(text)
    raw_chunks, buffer, buffer_tokens = [], [], 0

    for block in blocks:
        block_text = block["text"]
        block_section = block["section"]
        tokens = tokenizer.encode(block_text, add_special_tokens=False)

        if len(tokens) > max_tokens:
            words, sub_chunk, sub_tokens = block_text.split(), [], 0
            for word in words:
                word_tokens = tokenize_length(word)
                if sub_tokens + word_tokens > max_tokens:
                    raw_chunks.append({"text": " ".join(sub_chunk), "section": block_section})
                    sub_chunk, sub_tokens = [word], word_tokens
                else:
                    sub_chunk.append(word)
                    sub_tokens += word_tokens
            if sub_chunk:
                raw_chunks.append({"text": " ".join(sub_chunk), "section": block_section})
            continue

        if buffer_tokens + len(tokens) <= max_tokens:
            buffer.append(block_text)
            buffer_tokens += len(tokens)
        else:
            raw_chunks.append({"text": "\n\n".join(buffer), "section": block_section})
            buffer, buffer_tokens = [block_text], len(tokens)

    if buffer:
        raw_chunks.append({"text": "\n\n".join(buffer), "section": block_section})

    final_chunks = []
    for i, chunk in enumerate(raw_chunks):
        tokens = tokenizer.encode(chunk["text"], add_special_tokens=False)
        if len(tokens) > max_tokens:
            tokens = tokens[:max_tokens]

        if overlap > 0 and i > 0:
            prev_tokens = tokenizer.encode(final_chunks[-1]["text"], add_special_tokens=False)
            overlap_tokens = prev_tokens[-overlap:]
            tokens = overlap_tokens + tokens
            tokens = tokens[:max_tokens]

        final_chunks.append({
            "text": tokenizer.decode(tokens),
            "section": chunk["section"]
        })

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
    create_job(job_id=job_id, filename=job_id, total_chunks=len(chunks))
    mark_processing(job_id)

    for i, chunk in enumerate(chunks):
        payload = {
            "key": key,
            "filename": os.path.basename(key),
            "bucket": S3_BUCKET,
            "chunk_id": i,
            "total_chunks": len(chunks),
            "text": chunk["text"],
            "metadata": {
                "policy_number": os.path.splitext(os.path.basename(key))[0],
                "chunk_type": "table" if "[TABLE START]" in chunk["text"] else "text",
                "section": chunk["section"]
            }
        }
        print(f"📤 Publishing chunk {i+1}/{len(chunks)} for {key}, section={chunk['section']}")
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

# --- FastAPI App ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

polling_thread = None
polling_enabled = False

@app.post("/start-polling")
def start_polling():
    global polling_thread, polling_enabled
    if not polling_enabled:
        polling_enabled = True
        polling_thread = threading.Thread(target=poll_s3, daemon=True)
        polling_thread.start()
        return {"status": "started"}
    return {"status": "already running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
