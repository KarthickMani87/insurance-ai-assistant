import os

VECTOR_COLLECTION = os.getenv("VECTOR_COLLECTION", "insurance_docs")
VECTOR_POLICY_COLLECTION = os.getenv("POLICY_DB", "policies")
VECTOR_POLICY_SEARCH_KEY = os.getenv("POLICY_UNIQUE_SEARCH_KEY", "policy_number")
VECTOR_DB_HOST = os.getenv("VECTOR_DB_HOST", "vector-db")
VECTOR_DB_PORT = int(os.getenv("VECTOR_DB_PORT", 8000))

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

EMBED_MODEL = os.getenv("EMBED_MODEL", "mixedbread-ai/mxbai-embed-large-v1")
EMBEDDINGS_URL = os.getenv("EMBEDDINGS_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "none")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
KNN_SEARCH = int(os.getenv("KNN_SEARCH", 10))

LLM_LIGHT_MODEL= os.getenv("LLM_LIGHT_MODEL", "gemma:2b")
# --- Config ---
LLM_MODEL = os.getenv("LLM_MODEL", "mistral")
LLM_URL = os.getenv("LLM_URL", "http://host.docker.internal:11434")
