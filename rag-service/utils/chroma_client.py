from chromadb import HttpClient

# Initialize Chroma client
chroma_client = HttpClient(host="vector-db", port=8000)

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

