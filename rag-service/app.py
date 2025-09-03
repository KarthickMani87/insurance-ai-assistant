import os
import redis
import json
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from fastapi import APIRouter
from utils.memory_utils import HybridMemory

from graph_upload import upload_chain
from graph_conversation import conversation_chain
from services.email_service import send_email
from services.llm_service import extract_policy_metadata, extract_merged_policy_data, draft_fraud_alert, return_dummy
from utils.verify_policy import verify_policy, get_policy_from_db
from utils.chroma_client import retrieve_query
from utils.state_store import save_state, load_state
from utils.conversation_state import ConversationStateModel
from utils.cleanupFunc import collect_docs


from config import (
    VECTOR_COLLECTION,
    REDIS_HOST, REDIS_PORT,
    OPENAI_MODEL,
)

# --- FastAPI app ---
app = FastAPI(title="RAG Service")

# Enable CORS (so React frontend can call this)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Redis ---
redis_inst = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# --- Embeddings client (via TEI API) ---
print(f"Starting RAG Service")



def chunk_text(text: str, max_chars: int = 1000):
    """
    Splits text into smaller chunks so it fits within the LLM context window.
    max_chars is approximate — adjust based on model's 4096 token limit.
    """
    for i in range(0, len(text), max_chars):
        yield text[i:i + max_chars]

# --- Schemas ---
class UploadRequest(BaseModel):
    key: str

class QueryRequest(BaseModel):
    question: str
    policy_number: str
    conversation: list = []
    start_date: str | None = None
    end_date: str | None = None


# --- Helpers ---
@app.post("/upload")
def upload_doc(data: UploadRequest):
    """Check job status + return policy metadata once ready"""

    # --- 1. Ensure ingestion polling is running ---
    if not redis_inst.get("polling_started"):
        requests.post("http://ingestion-service:9000/start-polling")
        redis_inst.set("polling_started", "1")
        print("⚡ Ingestion polling started")

    # --- 2. Check ingestion job status ---
    job_id = os.path.basename(data.key)
    job_key = f"job:{job_id}"
    job = redis_inst.hgetall(job_key)

    if not job:
        return {
            "status": "pending",
            "chunks_done": 0,
            "total_chunks": 0,
            "message": "Processing document, please wait..."
        }

    if job["status"] != "complete":
        return {
            "status": job["status"],
            "chunks_done": int(job.get("chunks_done", 0)),
            "total_chunks": int(job.get("total_chunks", 0)),
            "message": "Processing document, please wait..."
        }

    # --- 3. Guard: check if extraction already done ---
    extracted_key = f"extracted:{job_id}"
    if redis_inst.exists(extracted_key):
        print(f"✅ Returning cached extraction for {job_id}")
        return json.loads(redis_inst.get(extracted_key))

    # --- 4. Run extraction once ---
    print(f"⚡ Running extraction for {job_id}")

    fields = {
        "policyholder_name": "Find the policyholder name (the contract owner).",
        "insured_person": "List all insured persons or covered individuals.",
        "policy_number": "Find the policy number.",
        "insurance_provider": "Find the insurance company/provider.",
        "policy_type": "Find the type of insurance policy (health, motor, life, travel, etc.).",
        "coverage": "List the coverage benefits provided by this policy.",
        "start_date": "Find the start date of the policy.",
        "end_date": "Find the expiry/end date of the policy."
    }

    document_texts = []

    for field, query_text in fields.items():
        results = retrieve_query(
            query_text,
            VECTOR_COLLECTION,
            mode="extraction",   # 👈 deterministic metadata mode
            top_k=3
        )
        docs = collect_docs(results)
        document_texts.extend(docs)


    # --- 5. Run extraction on retrieved chunks directly ---
    chunk_results = []
    for doc in document_texts:
        res = extract_policy_metadata(doc, model=OPENAI_MODEL)
        chunk_results.append(res)

    # Merge results
    final_extracted = extract_merged_policy_data(chunk_results, model=OPENAI_MODEL)
    print("Received Final Extracted:", final_extracted)

    if not final_extracted.get("policy_number"):
        response = {
            "status": "complete",
            "message": "❌ Not a valid insurance policy document."
        }
        redis_inst.set(extracted_key, json.dumps(response))
        return response

    # --- 6. Verify against DB ---
    verify_fields = ["policyholder_name", "policy_number", "insurance_provider",
                     "policy_type", "start_date", "end_date"]

    details = {f: final_extracted.get(f) for f in verify_fields}
    policy = get_policy_from_db(details)

    if not policy:
        response = {
            "status": "not_found",
            "message": "❌ Policy not found in database."
        }
        redis_inst.set(extracted_key, json.dumps(response))
        return response

    is_valid, messages = verify_policy(details, policy)
    if not is_valid:
        fraud_email = draft_fraud_alert(details, messages)
        send_email(fraud_email["subject"], fraud_email["body"])
        response = {
            "status": "error",
            "message": "⚠️ We could not verify this policy. Please contact support."
        }
        redis_inst.set(extracted_key, json.dumps(response))
        return response

    # --- 7. Success ---
    response = {
        "status": "complete",
        "message": "✅ Insurance policy verified successfully.",
        **{f: final_extracted.get(f) for f in fields}
    }
    redis_inst.set(extracted_key, json.dumps(response))
    return response


@app.post("/query")
def query(data: QueryRequest):
    """Interactive Q&A with Multi-Agent LangGraph"""

    def normalize_state(state):
        """Ensure LangGraph state is always a dict."""
        if isinstance(state, list):
            return state[0] if state else {}
        if not isinstance(state, dict):
            return {"answer": str(state)}
        return state

    # --- Load state from Redis ---
    stored_state = load_state(data.policy_number) or {}

    # --- Restore or create memory ---
    if "mem_vars" in stored_state:
        memory = HybridMemory.deserialize(stored_state["mem_vars"])
    else:
        memory = HybridMemory(buffer_k=5)

    stored_state["memory"] = memory

    # --- Prepare state for graph ---
    default_state = {
        "policy_number": data.policy_number,
        "policyholder_name": stored_state.get("policyholder_name"),
        "insurance_provider": stored_state.get("insurance_provider"),
        "policy_type": stored_state.get("policy_type"),
        "start_date": data.start_date or stored_state.get("start_date"),
        "end_date": data.end_date or stored_state.get("end_date"),
        "fraud": stored_state.get("fraud", False),
        "memory": stored_state["memory"],  # HybridMemory object
        "question": data.question,
    }

    print("=== Incoming Query ===")
    print(f"Policy: {data.policy_number}")
    print(f"Question: {data.question}")
    print("======================")

    # --- Run LangGraph ---
    raw_state = conversation_chain.invoke(default_state)
    new_state = normalize_state(raw_state)

    print("=== Graph Returned ===")
    print(f"Answer: {new_state.get('answer')}")
    print(f"[Router → {new_state.get('route', 'UNKNOWN_AGENT')}]")
    print("======================")

    # --- Save state back to Redis ---
    save_state(
        data.policy_number,
        {
            **{k: v for k, v in new_state.items() if k not in ("memory", "mem_vars")},
            "mem_vars": memory.serialize(),  # JSON-safe memory snapshot
        },
    )

    # --- Only return the final RAG answer ---
    return {"answer": new_state.get("answer", "No response available.")}

