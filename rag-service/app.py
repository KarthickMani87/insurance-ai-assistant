from fastapi import FastAPI
from pydantic import BaseModel
from chromadb import HttpClient
from graph_upload import upload_chain
from graph_conversation import conversation_chain
from services.email_service import send_summary_email

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="RAG Service")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #["http://localhost:5173"],  # Your React app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to Chroma
chroma_client = HttpClient(host="vector-db", port=8000)
collection = chroma_client.get_or_create_collection("insurance_docs")

class UploadRequest(BaseModel):
    document_text: str

class QueryRequest(BaseModel):
    question: str
    policy_number: str
    conversation: list = []
    start_date: str | None = None
    end_date: str | None = None

def retrieve_policy_chunks(policy_number: str, question: str, top_k: int = 3):
    results = collection.query(
        query_texts=[question],
        n_results=top_k,
        where={"policy_number": policy_number}
    )
    return "\n".join(results.get("documents", [[]])[0])

@app.post("/upload")
def upload_doc(data: UploadRequest):
    """Initial extraction right after upload"""
    state = upload_chain.invoke({"document_text": data.document_text})
    return state

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
    next_step = "Proceed with claims"  # Can be refined with LLM
    send_summary_email(data.conversation, conclusion, next_step)
    return {"message": "Summary sent to backend team"}
