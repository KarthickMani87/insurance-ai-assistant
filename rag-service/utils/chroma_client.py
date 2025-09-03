import os
import requests
from chromadb import HttpClient
from sentence_transformers import CrossEncoder

from config import (
    VECTOR_DB_HOST, VECTOR_DB_PORT,
    EMBED_MODEL, EMBEDDINGS_URL,
    KNN_SEARCH, VECTOR_POLICY_COLLECTION,
)

VECTOR_DB_HOST = os.getenv("VECTOR_DB_HOST", "vector-db")
VECTOR_DB_PORT = int(os.getenv("VECTOR_DB_PORT", 8000))

# Load reranker model (fast and accurate for reranking)
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


# Initialize Chroma client
chroma_client = HttpClient(host=VECTOR_DB_HOST, port=VECTOR_DB_PORT)

def get_vectorDB_collection_instance(collection_name):
    # Collection for insurance docs
    return chroma_client.get_or_create_collection(collection_name)

def retrieve_query(
    query_text,
    collection_name,
    mode: str = "qa",   # "qa" or "extraction"
    top_k: int = 5,
    where: dict | None = None,
):
    """
    Query ChromaDB for relevant chunks of a given policy.

    Modes:
        - "qa": for conversational Q&A, recall-focused.
          Fetch 20 candidates, rerank with cross-encoder, return top_k.
        - "extraction": for structured policy metadata extraction.
          Fetch only 2 raw chunks (no reranking), return them directly.

    Args:
        query_text: user query or extraction question
        collection_name: Chroma collection name
        mode: "qa" or "extraction"
        top_k: how many docs to return
        where: optional metadata filter (e.g., {"section": "SCHEDULE"})
    """
    # Step 1: Get embedding
    payload = {"model": EMBED_MODEL, "input": query_text}
    resp = requests.post(EMBEDDINGS_URL, json=payload, timeout=30)
    resp.raise_for_status()
    query_vector = resp.json()["data"][0]["embedding"]

    collection = get_vectorDB_collection_instance(collection_name)

    # --- Mode: extraction (fast, precise, no reranking)
    if mode == "extraction":
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=3,
            #where=where,
            include=["documents", "metadatas", "distances"],
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        if not docs:
            print("[retrieve_query] ❌ No results for extraction")
            return []
        return [{"text": d, "metadata": m, "score": None} for d, m in zip(docs, metas)][:top_k]

    # --- Mode: qa (deep search + rerank)
    elif mode == "qa":
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=20,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not docs:
            print("[retrieve_query] ❌ No results for QA")
            return []

        # Rerank
        pairs = [[query_text, doc] for doc in docs]
        scores = reranker.predict(pairs)
        reranked = sorted(zip(docs, metas, scores), key=lambda x: x[2], reverse=True)
        return [{"text": d, "metadata": m, "score": s} for d, m, s in reranked[:top_k]]

    else:
        raise ValueError(f"Invalid mode: {mode}")


def retrieve_get(unique_key):

    policy_client = get_vectorDB_collection_instance(VECTOR_POLICY_COLLECTION)

    # Deterministic lookup by policy number (safe, no embeddings needed)
    policy_result = policy_client.get(
        where={"policy_number": unique_key}
    )

    return policy_result


