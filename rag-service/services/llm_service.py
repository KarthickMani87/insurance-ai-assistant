import json
import re
import os
import requests
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_ollama import OllamaLLM
from langchain_core.output_parsers import StrOutputParser
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel
from typing import Optional, List, Dict

LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"  # default local embedding model
)

LLM_URL = os.getenv(
    "LLM_URL",
    "http://host.docker.internal:11434"  # default local embedding model
)

#llm = Ollama(model=LLM_MODEL, base_url="http://ollama:11434")

llm = OllamaLLM(
    model=LLM_MODEL,
    base_url=LLM_URL,
    request_timeout=300,
    options={"stream": False}
)

print(f"LLM {LLM_MODEL} and LLM URL {LLM_URL}")



def extract_policy_metadata(document: str) -> dict:
    
    class PolicyMetadata(BaseModel):
        policyholder_name: Optional[str] = None
        policy_number: Optional[str] = None
        insured_person: Optional[List[str]] = None
        policy_type: Optional[str] = None
        coverage: Optional[str] = None
        start_date: Optional[str] = None
        end_date: Optional[str] = None
            
    parser = JsonOutputParser(pydantic_object=PolicyMetadata)

    prompt = """
    You are an expert assistant for insurance policies.

    Extract the following fields from the policy text below.
    Policy holder name, policy type, policy number, expiry date, convert to start date
    and end date.
    Return ONLY valid JSON, no explanations, no markdown.

    {format_instructions}

    Policy text:
    {document}
    """

    print("extract_policy_metadata")

    prompt_template = PromptTemplate(
        template=prompt,
        input_variables=["document"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    print("Calling Chain invoke-0")
    chain = prompt_template | llm | parser

    try:
        result = chain.invoke({"document": document})
        print("✅ Got structured JSON:", result)
        return result
    except Exception as e:
        print("❌ Metadata extraction failed:", e)
        return {
            "policyholder_name": None,
            "policy_number": None,
            "insured_person": [],
            "policy_type": None,
            "coverage": None,
            "start_date": None,
            "end_date": None,
        }

def extract_merged_policy_data(chunk_results: List[Dict]) -> dict:
    # ✅ Final schema, all optional
    class FinalPolicyMetadata(BaseModel):
        policyholder_name: Optional[str] = None
        insured_person: Optional[List[str]] = None
        policy_number: Optional[str] = None
        policy_type: Optional[str] = None
        coverage: Optional[str] = None
        start_date: Optional[str] = None
        end_date: Optional[str] = None

    # JSON parser bound to schema
    parser = JsonOutputParser(pydantic_object=FinalPolicyMetadata)

    # Merge prompt — STRICT JSON only
    merge_prompt = PromptTemplate(
        template="""
You are an expert assistant for insurance policies.

You will be given multiple JSON objects (from different chunks of the same document).
Each object may have partial or conflicting data. Your task is to MERGE them into ONE final JSON.

RULES:
- Output ONLY valid JSON (no explanations, no markdown, no code fences).
- Each field must have a SINGLE value (string or null), not an array.
- If multiple values appear:
  - Prefer the most specific and complete value.
  - Prefer real dates/numbers over placeholders like "Not specified".
  - For names, choose the most complete (e.g., "Mr. John Smith" over "John").
  - For policy_type/coverage, choose the clearest or most detailed phrasing.
- If nothing valid, return null.

Schema:
{format_instructions}

Partial results:
{chunk_results}
""",
        input_variables=["chunk_results"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    merge_chain = merge_prompt | llm | parser

    try:
        final_metadata = merge_chain.invoke({"chunk_results": str(chunk_results)})
        print("✅ Final merged metadata:", final_metadata)
        return final_metadata
    except Exception as e:
        print("❌ Merge failed:", e)
        # Return empty schema if fail
        return {
            "policyholder_name": None,
            "policy_number": None,
            "insured_person": [],
            "policy_type": None,
            "coverage": None,
            "start_date": None,
            "end_date": None,
        }
    

def draft_fraud_alert(details: dict, errors: list):
    subject = f"Fraud Alert – Policy {details['policy_number']}"

   # Precompute the joined error lines
    if errors:
        error_lines = "\n".join([f"    {err}" for err in errors])
    else:
        error_lines = "    ✅ No discrepancies found."

    body = f"""Dear Compliance and Fraud Prevention Team,

        We detected potential forgery or misuse in Policy Number {details['policy_number']}.

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