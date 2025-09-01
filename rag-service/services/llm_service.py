import json
import re
import os
import requests
from typing import Optional, List, Dict
from pydantic import BaseModel


from langchain_core.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_ollama import OllamaLLM
from langchain_core.output_parsers import JsonOutputParser
from langchain.output_parsers import OutputFixingParser

from utils.cleanupFunc import clean_value, clean_name, normalize_date

from config import LLM_MODEL, LLM_URL

llm = OllamaLLM(
    model=LLM_MODEL,
    base_url=LLM_URL,
    request_timeout=300,
    options={"stream": False}
)

print(f"🚀 LLM {LLM_MODEL} at {LLM_URL}")


def call_llm(prompt: str, model: str = None) -> str:
    """
    Call an LLM REST API (Ollama by default).
    - Defaults to the model set in env (mistral).
    - Override with `model` param for per-call flexibility.
    """

    model_name = model or LLM_MODEL

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }

    try:
        resp = requests.post(f"{LLM_URL}/api/generate", json=payload, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "").strip()
    except Exception as e:
        print(f"❌ LLM call failed: {e}")
        return "⚠️ LLM service unavailable."
    
# --- Schema ---
class PolicyMetadata(BaseModel):
    policyholder_name: Optional[str] = None
    policy_number: Optional[str] = None
    insured_person: Optional[List[str]] = None
    policy_type: Optional[str] = None
    coverage: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


def return_dummy():
    # ✅ Hard-coded mock policy metadata
    return PolicyMetadata(
                policyholder_name="Karthick Mani",
                policy_number="AUTH12345",
                insured_person=["Karthick Mani"],  # optional, but included for consistency
                policy_type="Health Recharge",
                coverage=["Hospitalization up to INR 25,00,000 with deductible INR 5,00,000"],
                start_date="2025-08-03",
                end_date="2026-08-02"
            ).dict()

# --- Helpers ---
def _safe_normalize(result: dict) -> dict:
    """Normalize raw parsed values."""
    return {
        "policyholder_name": clean_name(clean_value(result.get("policyholder_name"))),
        "policy_number": clean_value(result.get("policy_number")),
        "insured_person": result.get("insured_person") or [],
        "policy_type": clean_value(result.get("policy_type")),
        "coverage": result.get("coverage") or [],
        "start_date": normalize_date(clean_value(result.get("start_date"))),
        "end_date": normalize_date(clean_value(result.get("end_date"))),
    }


# --- Extraction ---
def extract_policy_metadata(document: str) -> dict:
    parser = JsonOutputParser(pydantic_object=PolicyMetadata)
    fixing_parser = OutputFixingParser.from_llm(parser=parser, llm=llm)

    prompt = """
You are an expert assistant for insurance policies.

Extract the following fields from the policy text below:
- policyholder_name
- policy_number
- insured_person
- policy_type
- coverage
- start_date
- end_date

STRICT RULES:
- Output ONLY valid JSON (no markdown, no code fences, no explanations, no comments).
- Do NOT guess or assume values. If unclear, use null.
- Dates must remain exactly as in text; do NOT invent.

{format_instructions}

Policy text:
{document}
"""

    chain = PromptTemplate(
        template=prompt,
        input_variables=["document"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    ) | llm | fixing_parser

    try:
        raw = chain.invoke({"document": document})
        return _safe_normalize(raw)
    except Exception as e:
        print("❌ Metadata extraction failed:", e)
        return PolicyMetadata().dict()


# --- Merge ---
def extract_merged_policy_data(chunk_results: List[Dict]) -> dict:
    parser = JsonOutputParser(pydantic_object=PolicyMetadata)
    fixing_parser = OutputFixingParser.from_llm(parser=parser, llm=llm)

    merge_prompt = """
Extract the following fields from the policy text below:

- policyholder_name: The full name of the main policyholder. Remove titles (Mr., Ms., Mrs., Dr.).
- policy_number: The official policy number. If not present, return null.
- insured_person: A list of real person names covered under the policy. 
  • Do not include placeholders like "The insured person", "Policyholder", or "Name and address...".
  • Remove titles (Mr., Ms., Mrs., Dr.).
  • Return [] if none are listed.
- policy_type: Type of insurance (Health, Life, etc.), null if unclear.
- coverage: List of coverage items (hospitalization, accident, etc.). Do not return amounts here.
- start_date: Explicit start date as given, null if not found.
- end_date: Explicit end date as given, null if not found.

STRICT RULES:
- Output ONLY valid JSON (no explanations, no markdown, no comments).
- Do not guess or assume values. If unclear, use null or [].


Schema:
{format_instructions}

Partial results:
{chunk_results}
"""

    chain = PromptTemplate(
        template=merge_prompt,
        input_variables=["chunk_results"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    ) | llm | fixing_parser

    try:
        raw = chain.invoke({"chunk_results": str(chunk_results)})
        return _safe_normalize(raw)
    except Exception as e:
        print("❌ Merge failed:", e)
        return PolicyMetadata().dict()


def draft_fraud_alert(details: dict, errors: list):
    subject = f"Fraud Alert – Policy {details.get('policy_number', 'UNKNOWN')}"

    if errors:
        error_lines = "\n".join([f"    {err}" for err in errors])
    else:
        error_lines = "    ✅ No discrepancies found."

    body = f"""Dear Compliance and Fraud Prevention Team,

We detected potential forgery or misuse in Policy Number {details.get('policy_number', 'UNKNOWN')}.

Discrepancies:
{error_lines}

Please investigate immediately to ensure the integrity of our records.

Best regards,  
Automated Fraud Detection System
"""
    return {"subject": subject.strip(), "body": body.strip()}


'''
def draft_fraud_alert(details: dict, errors: list):
    """
    Build a fraud alert email using LLM.
    Always returns a dict with subject + body.
    """

    template = """
    You are an expert fraud detection assistant.

    Task:
    Draft a professional fraud alert email using ONLY the facts below. 
    Do NOT add or invent any values — use the discrepancies exactly as given.
    Company Name: National Insurance, Sender: Auto generated Mail.

    Rules:
    - Output plain text only (not JSON).
    - Subject must include "Fraud Alert" and the policy number.
    - Mention the policy number clearly in the body.
    - Explain that a forged/misused insurance policy was detected.
    - List mismatched fields clearly with both expected and found values.
    - End with: "Please investigate immediately."
    - If the policyholder name contains prefixes like "Mr.", "Mrs.", "Ms.", "Dr.", remove them before output.
    - For insured_person: Only return actual names, not placeholders (like "The insured person").
    - Return [] if no valid names are found.

    Policy Details:
    Policy Number: {policy_number}
    Policyholder Name: {policyholder_name}
    Policy Type: {policy_type}
    Start Date: {start_date}
    End Date: {end_date}

    Issues Found:
    {errors}
    """

    mail_prompt = PromptTemplate(
        template=template,
        input_variables=[
            "policy_number",
            "policyholder_name",
            "policy_type",
            "start_date",
            "end_date",
            "errors",
        ],
    )

    mail_chain = mail_prompt | llm

    raw_email = mail_chain.invoke({
        "policy_number": details.get("policy_number", "N/A"),
        "policyholder_name": details.get("policyholder_name", "N/A"),
        "policy_type": details.get("policy_type", "N/A"),
        "start_date": details.get("start_date", "N/A"),
        "end_date": details.get("end_date", "N/A"),
        "errors": "\n".join(errors) if errors else "No mismatches found.",
    })

    # Simple parsing: subject is always first line starting with "Subject:"
    subject, body = "Fraud Alert – Policy Verification", raw_email
    for line in raw_email.splitlines():
        if line.lower().startswith("subject:"):
            subject = line.replace("Subject:", "").strip()
            # everything after goes to body
            body = raw_email.split("\n", 1)[1].strip() if "\n" in raw_email else ""
            break

    return {"subject": subject, "body": body}

'''