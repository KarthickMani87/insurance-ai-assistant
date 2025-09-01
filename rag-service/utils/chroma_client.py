import os
import requests
from chromadb import HttpClient

from config import (
    VECTOR_DB_HOST, VECTOR_DB_PORT,
    EMBED_MODEL, EMBEDDINGS_URL,
    KNN_SEARCH, VECTOR_POLICY_COLLECTION,
)

VECTOR_DB_HOST = os.getenv("VECTOR_DB_HOST", "vector-db")
VECTOR_DB_PORT = int(os.getenv("VECTOR_DB_PORT", 8000))

# Initialize Chroma client
chroma_client = HttpClient(host=VECTOR_DB_HOST, port=VECTOR_DB_PORT)

def get_vectorDB_collection_instance(collection_name):
    # Collection for insurance docs
    return chroma_client.get_or_create_collection(collection_name)

def retrieve_query(query_text, collection_name):
    """
    Query ChromaDB for relevant chunks of a given policy.
    """
    payload = {"model": EMBED_MODEL, "input": query_text}
    resp = requests.post(EMBEDDINGS_URL, json=payload, timeout=30)
    resp.raise_for_status()
     
    query_vector = resp.json()["data"][0]["embedding"]

    collection = get_vectorDB_collection_instance(collection_name)
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=KNN_SEARCH,
        where_document={"$contains": "policy"},   # basic keyword filter
        include=["documents", "metadatas", "distances"],
    )

    return results

def retrieve_get(unique_key):

    policy_client = get_vectorDB_collection_instance(VECTOR_POLICY_COLLECTION)

    # Deterministic lookup by policy number (safe, no embeddings needed)
    policy_result = policy_client.get(
        where={"policy_number": unique_key}
    )

    return policy_result


