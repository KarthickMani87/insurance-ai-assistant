import os
import requests
from typing import Optional, List, Dict

from .chroma_client import get_policy_instance

EMBED_MODEL = os.getenv("EMBED_MODEL", "mixedbread-ai/mxbai-embed-large-v1")
EMBEDDINGS_URL = os.getenv("EMBEDDINGS_URL")

def verify_policy(details: dict):
    """
    Verify extracted policy details against the Chroma DB.
    details: dict extracted from LLM
    """

    errors = []

    policy_client = get_policy_instance()

    # Deterministic lookup by policy number (safe, no embeddings needed)
    policy_result = policy_client.get(
        where={"policy_number": details.get("policy_number")}
    )

    if not policy_result or not policy_result.get("metadatas"):
        return False, ["❌ No policy found in database"]

    policy = policy_result["metadatas"][0]    

    # Fields to compare: (field_name, label, normalize)
    fields_to_check = [
        ("policyholder_name", "Policyholder name", str.lower),
        ("policy_type", "Policy type", str.lower),
        ("start_date", "Start date", str),
        ("end_date", "End date", str),
    ]

    # Run comparisons
    for field, label, normalizer in fields_to_check:
        expected = policy.get(field)
        found = details.get(field)

        if expected and found:
            if normalizer(str(expected).strip()) != normalizer(str(found).strip()):
                errors.append(f"❌ {label} mismatch (Expected: {expected}; Found: {found})")

    # Final result
    if errors:
        return False, errors
    return True, ["✅ Policy verified successfully"]
