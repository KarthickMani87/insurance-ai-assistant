import json
import redis
from config import REDIS_HOST, REDIS_PORT

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def save_state(session_id: str, state: dict):
    """Save conversation state in Redis"""
    redis_client.set(f"conv:{session_id}", json.dumps(state))

def load_state(session_id: str) -> dict:
    """Load conversation state from Redis"""
    raw = redis_client.get(f"conv:{session_id}")
    return json.loads(raw) if raw else {}
