import os
import redis
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from chromadb import HttpClient
from langchain_openai import OpenAIEmbeddings
from fastapi.middleware.cors import CORSMiddleware

from graph_upload import upload_chain
from graph_conversation import conversation_chain
from services.email_service import send_summary_email
from services.llm_service import extract_policy_metadata, extract_merged_policy_data, draft_fraud_alert, return_dummy
from utils.verify_policy import verify_policy
from services.email_service import send_summary_email
from utils.chroma_client import retrieve_query
from utils.state_store import save_state, load_state
from utils.conversation_state import ConversationStateModel
from utils.cleanupFunc import collect_docs


from config import (
    VECTOR_COLLECTION,
    REDIS_HOST, REDIS_PORT,
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
    job_id = os.path.basename(data.key)   # ✅ normalize
    job_key = f"job:{job_id}"
    job = redis_inst.hgetall(job_key)

    '''
    if not job:
        return {"status": "not_found", "message": "No processing job found for this file."}

    if job["status"] != "complete":
        return {
            "status": job["status"],
            "chunks_done": int(job.get("chunks_done", 0)),
            "total_chunks": int(job.get("total_chunks", 0)),
            "message": "Processing document, please wait..."
        }
    
    '''

    # --- Retrieve relevant chunks semantically ---
    query_text = (
        "Extract policy holder name, policy number, policy type, coverage, expiry dates, Policy issuer "
        "from this insurance policy document."
    )

    #query_vector = embedder.embed_query(query_text)

    results = retrieve_query(query_text, VECTOR_COLLECTION)

    docs = collect_docs(results)
    document_text = "\n".join(docs)
    #print("document text extracted:", document_text)

    if False:
        # Step 1: Chunk
        chunk_results = []
        for chunk in chunk_text(document_text, max_chars=2500):  # keep each chunk small
            res = extract_policy_metadata(chunk)
            chunk_results.append(res)

        # Step 2: Merge
        final_extracted = extract_merged_policy_data(chunk_results)


        print("Received Final Extracted: ", final_extracted)

        #print("Prtint Extracted Data: ", extracted)
        '''
        # --- Save extracted metadata back into Chroma ---
        if results.get("ids"):
            collection.update(
                ids=results["ids"],
                metadatas=[extracted for _ in results["ids"]]
            )
        '''

        # --- Final check ---
        if not final_extracted.get("policy_number"):
            return {
                "status": "complete",
                "message": "This document does not appear to be an insurance policy. Please upload a valid policy document."
            }

    required_fields = [
        "policyholder_name",
        "policy_number",
        "insured_person", 
        "policy_type",
        "coverage",
        "start_date",
        "end_date",
    ]

    verify_required_fields = [
        "policyholder_name",
        "policy_number",
        "policy_type",
        "start_date",
        "end_date",
    ]

    final_extracted = return_dummy()

    details = {field: final_extracted.get(field) for field in verify_required_fields}

    # Call verify_policy with details
    is_valid, messages = verify_policy(details) 

    if not is_valid:
        # 📝 Draft fraud alert with LLM (subject + body JSON)
        fraud_email = draft_fraud_alert(details, messages)

        # 📧 Send to backend team
        send_summary_email(fraud_email["subject"], fraud_email["body"])    

    return {
        "status": "complete",
        "message": "Insurance policy processed successfully.",
        **{field: final_extracted.get(field) for field in required_fields},
    }

@app.post("/query")
def query(data: QueryRequest):
    """Interactive Q&A with Multi-Agent LangGraph"""

    # Load existing conversation state from Redis (or empty dict if none)
    state = load_state(data.policy_number) or {}

    # Ensure required fields exist
    default_state = {
        "policy_number": data.policy_number,
        "policyholder_name": state.get("policyholder_name"),
        "policy_type": state.get("policy_type"),
        "start_date": data.start_date or state.get("start_date"),
        "end_date": data.end_date or state.get("end_date"),
        "history": state.get("history", []),
        "fraud": state.get("fraud", False),
    }

    # Always update with latest question
    default_state.update({
        "question": data.question,
    })

    # --- Debug log before graph ---
    print("=== Incoming Query ===")
    print(f"Policy: {data.policy_number}")
    print(f"Question: {data.question}")
    print(f"Policy Type: {default_state.get('policy_type')}")
    print("======================")

    # Run LangGraph
    new_state = conversation_chain.invoke(default_state)

    # --- Debug log after router ---
    print(f"[Router → {new_state.get('route', 'UNKNOWN_AGENT')}]")

    # Save updated state back to Redis
    save_state(data.policy_number, new_state)

    return new_state


@app.post("/summary")
def send_summary(data: QueryRequest):
    """Send summary to backend team at end of conversation"""
    summary = f"Policy {data.policy_number}, Conversation: {data.conversation}"
    conclusion = "Conversation completed"
    next_step = "Proceed with claims"  # could be refined with LLM
    send_summary_email(data.conversation, conclusion, next_step)
    return {"message": "Summary sent to backend team"}
