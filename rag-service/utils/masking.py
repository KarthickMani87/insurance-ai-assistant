import re
import hashlib
from typing import Dict
import spacy

# Load spaCy multilingual model (covers global names)
# ⚠️ run once: python -m spacy download xx_ent_wiki_sm
nlp = spacy.load("xx_ent_wiki_sm")


# --- Helper: deterministic ID from value (stable masking) ---
def _make_token(value: str, prefix: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{digest}"


def mask_text(text: str, mapping: Dict[str, str]) -> str:
    """
    Mask sensitive data in insurance documents.
    - Policy numbers (regex)
    - Dates (regex)
    - Names (NER via spaCy)
    """

    # --- Policy numbers (e.g., POL12345, 33346528202502, NBHHLIP22156V032122) ---
    for match in re.findall(r"\b(?:POL|NBHHLIP)\w+\b|\b\d{8,}\b", text):
        token = _make_token(match, "POLICY")
        mapping[token] = match
        text = text.replace(match, token)

    # --- Dates (dd/mm/yyyy, yyyy-mm-dd, Month dd, yyyy) ---
    date_pattern = r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}, \d{4})\b"
    for match in re.findall(date_pattern, text):
        token = _make_token(match, "DATE")
        mapping[token] = match
        text = text.replace(match, token)

    # --- Names (NER with spaCy multilingual model) ---
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "PER":  # "PER" = Person in multilingual model
            name = ent.text
            if name not in mapping.values():  # avoid double masking
                token = _make_token(name, "PERSON")
                mapping[token] = name
                text = text.replace(name, token)

    return text


def unmask_text(text: str, mapping: Dict[str, str]) -> str:
    """
    Replace placeholders back with original values.
    """
    for token, original in mapping.items():
        text = text.replace(token, original)
    return text


# --- Example Usage ---
if __name__ == "__main__":
    doc = "Policy Number POL12345 issued to Vanaja Mani Arumugam and Abdul Rahman Al-Saud on 03/08/2025."
    mapping = {}
    masked = mask_text(doc, mapping)
    print("Masked:", masked)
    print("Mapping:", mapping)

    # Simulate LLM returning masked result
    llm_output = "PERSON_a1b2c3 is covered under POLICY_d4e5f6 starting DATE_f7g8h9."
    unmasked = unmask_text(llm_output, mapping)
    print("Unmasked:", unmasked)
