from typing import Optional, List, Dict
from utils.chroma_client import retrieve_get

from config import VECTOR_POLICY_SEARCH_KEY


def get_policy_from_db(details: dict):
    """
    Retrieve a policy record from Chroma DB.
    Returns policy metadata dict if found, else None.
    """
    policy_result = retrieve_get(details.get(VECTOR_POLICY_SEARCH_KEY))

    if not policy_result or not policy_result.get("metadatas"):
        return None
    
    return policy_result["metadatas"][0]

def verify_policy(details: dict, policy: dict):
    """
    Compare extracted policy details against a given policy record.
    Returns (is_valid: bool, messages: list).
    """
    errors = []

    fields_to_check = [
        ("policyholder_name", "Policyholder name", str.lower),
        ("policy_type", "Policy type", str.lower),
        ("start_date", "Start date", str),
        ("end_date", "End date", str),
    ]

    for field, label, normalizer in fields_to_check:
        expected = policy.get(field)
        found = details.get(field)

        if expected and found:
            norm_expected = normalizer(str(expected).strip())
            norm_found = normalizer(str(found).strip())

            # ✅ allow partial matches in either direction
            if norm_expected not in norm_found and norm_found not in norm_expected:
                errors.append(f"❌ {label} mismatch (Expected: {expected}; Found: {found})")

    if errors:
        return False, errors
    return True, ["✅ Policy verified successfully"]

