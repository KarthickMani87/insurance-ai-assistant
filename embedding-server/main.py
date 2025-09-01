import os
import torch
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Union, List
from transformers import AutoTokenizer, AutoModel

app = FastAPI()

# Enable CORS (use restrictive origins in production!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model/tokenizer
tokenizer = None
model = None

MAX_TOKEN = int(os.getenv("MAX_TOKEN", "384"))

@app.on_event("startup")
async def load_model():
    """Load HuggingFace embedding model once at startup."""
    global tokenizer, model
    model_name = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    print(f"🚀 Loading embedding model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    model = AutoModel.from_pretrained(model_name, local_files_only=True)
    model.eval()
    print("✅ Model loaded successfully!")


# --- OpenAI-style request schema ---
class EmbeddingRequest(BaseModel):
    model: str
    input: Union[str, List[str]]  # OpenAI allows string or list of strings


@app.post("/v1/embeddings")
async def create_embeddings(req: EmbeddingRequest, request: Request):
    """OpenAI-compatible embeddings endpoint."""

    # Debug raw body (optional, can comment out later)
    body = await request.json()
    #print("📩 RAW REQUEST:", body)

    # Normalize input → always a list of strings
    if isinstance(req.input, str):
        texts = [req.input]
    elif isinstance(req.input, list):
        if not all(isinstance(x, str) for x in req.input):
            raise HTTPException(status_code=422, detail="All items in input list must be strings")
        texts = req.input
    else:
        raise HTTPException(status_code=400, detail="Invalid input type")

    # Tokenize
    inputs = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=MAX_TOKEN,
        return_tensors="pt"
    )

    # Compute embeddings (mean pooling)
    with torch.no_grad():
        embeddings = model(**inputs).last_hidden_state.mean(dim=1).tolist()

    # Build OpenAI-style response
    data = [
        {"object": "embedding", "embedding": emb, "index": i}
        for i, emb in enumerate(embeddings)
    ]

    usage = {
        "prompt_tokens": int(inputs["input_ids"].numel()),
        "total_tokens": int(inputs["input_ids"].numel()),
    }

    return {
        "object": "list",
        "data": data,
        "model": req.model,
        "usage": usage,
    }
