import os
from chromadb import HttpClient
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

VECTOR_DB_HOST = os.getenv("VECTOR_DB_HOST", "vector-db")
VECTOR_DB_PORT = int(os.getenv("VECTOR_DB_PORT", 8000))


# Initialize Chroma client
chroma_client = HttpClient(host=VECTOR_DB_HOST, port=VECTOR_DB_PORT)

# Collection for insurance docs
collection = chroma_client.get_or_create_collection("insurance_docs")

def retrieve_policy_chunks(policy_number: str, query: str, top_k: int = 3):
    """
    Query ChromaDB for relevant chunks of a given policy.
    """
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where={"policy_number": policy_number}  # filter on metadata
    )
    docs = results.get("documents", [[]])[0]
    return "\n".join(docs)


def get_policy_instance():
    return chroma_client.get_collection("policies")

