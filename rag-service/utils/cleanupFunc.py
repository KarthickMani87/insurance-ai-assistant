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


def collect_docs(results: dict) -> list[str]:
    """
    Flatten and deduplicate documents from a Chroma query response.
    Handles both single-query and multi-query results.
    """
    docs = []
    if results and "documents" in results:
        for doc_list in results["documents"]:   # one list per query
            for chunk in doc_list:
                if chunk not in docs:           # avoid duplicates
                    docs.append(chunk)
    return docs
