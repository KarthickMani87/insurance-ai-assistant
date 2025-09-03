import re
from datetime import datetime
from dateutil import parser as dateparser  # more flexible date parsing
from typing import Optional, List, Dict

def clean_value(val):
    """Normalize placeholder values into None, handle list inputs."""
    if not val:
        return None
    if isinstance(val, list):   # ✅ handle list case
        val = " ".join([str(v) for v in val if v])
    val = str(val).strip()
    if val.lower() in ["na", "n/a", "none", "not specified", ""]:
        return None
    return val

def clean_name(name):
    """Remove titles like Mr., Dr., etc. Handles lists too."""
    if not name:
        return None
    if isinstance(name, list):
        name = " ".join([str(v) for v in name if v])
    cleaned = re.sub(r"^(mr\.|mrs\.|ms\.|dr\.)\s*", "", str(name).strip(), flags=re.IGNORECASE)
    return cleaned or None

def normalize_date(date_str: Optional[str]) -> Optional[str]:
    """Convert dates into YYYY-MM-DD if possible."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str, dayfirst=True, fuzzy=True)  # robust parsing
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def collect_docs(results, with_metadata=False):
    """
    Collect docs from retrieval results.
    Supports both reranked list format and raw Chroma dict format.
    """
    if not results:
        return []

    collected = []

    # Case 1: reranked list format
    if isinstance(results, list) and results and isinstance(results[0], dict):
        for r in results:
            if with_metadata:
                collected.append(r)
            else:
                collected.append(r.get("text", ""))
        return collected

    # Case 2: raw Chroma dict
    if isinstance(results, dict) and "documents" in results:
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        for d, m in zip(docs, metas):
            collected.append({"text": d, "metadata": m} if with_metadata else d)
        return collected

    print("[collect_docs] ⚠️ Unexpected results format:", type(results))
    return []


