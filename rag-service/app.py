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
from services.llm_service import extract_policy_metadata, extract_merged_policy_data, draft_fraud_alert
from utils.verify_policy import verify_policy
from services.email_service import send_summary_email

# --- Load env variables ---
VECTOR_COLLECTION = os.getenv("VECTOR_COLLECTION", "insurance_docs")
VECTOR_DB_HOST = os.getenv("VECTOR_DB_HOST", "vector-db")
VECTOR_DB_PORT = int(os.getenv("VECTOR_DB_PORT", 8000))

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

EMBED_MODEL = os.getenv("EMBED_MODEL", "mixedbread-ai/mxbai-embed-large-v1")
EMBEDDINGS_URL = os.getenv("EMBEDDINGS_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "none")
KNN_SEARCH = int(os.getenv("KNN_SEARCH", 10))

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

# --- Connect to Chroma ---
chroma_client = HttpClient(host=VECTOR_DB_HOST, port=VECTOR_DB_PORT)
collection = chroma_client.get_or_create_collection(name=VECTOR_COLLECTION)

# --- Redis ---
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# --- Embeddings client (via TEI API) ---
print(f"🔗 Using embeddings model: {EMBED_MODEL}")


def collect_docs(results: dict) -> list[str]:
    """
    Flatten and deduplicate documents from a Chroma query response.
    Handles both single-query and multi-query results.
    """
    docs = []
    if results and "documents" in results:
        for doc_list in results["documents"]:   # one list per query
            for chunk in doc_list:
                if chunk not in docs:           # avoid duplicates
                    docs.append(chunk)
    return docs

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
    job = r.hgetall(job_key)

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

    payload = {"model": EMBED_MODEL, "input": query_text}
    resp = requests.post(EMBEDDINGS_URL, json=payload, timeout=30)
    resp.raise_for_status()
     
    query_vector = resp.json()["data"][0]["embedding"]

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=KNN_SEARCH,
        where_document={"$contains": "policy"},   # basic keyword filter
        include=["documents", "metadatas", "distances"],
    )

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

    final_extracted = {
        "policyholder_name": "David",
        "policy_number": "POL10005",
        "insured_person": ["David"],
        "policy_type": "Health Insurance",
        "coverage": "All",
        "start_date": "2024-09-09",
        "end_date": "2025-09-08",}    

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
    """Interactive Q&A"""
    context = retrieve_policy_chunks(data.policy_number, data.question)
    state = conversation_chain.invoke({
        "question": data.question,
        "document_text": context,
        "start_date": data.start_date,
        "end_date": data.end_date
    })
    return state


@app.post("/summary")
def send_summary(data: QueryRequest):
    """Send summary to backend team at end of conversation"""
    summary = f"Policy {data.policy_number}, Conversation: {data.conversation}"
    conclusion = "Conversation completed"
    next_step = "Proceed with claims"  # could be refined with LLM
    send_summary_email(data.conversation, conclusion, next_step)
    return {"message": "Summary sent to backend team"}
