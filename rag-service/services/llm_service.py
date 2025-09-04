import os
import requests
from typing import Optional, List, Dict
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain.output_parsers import OutputFixingParser

from utils.cleanupFunc import clean_value, clean_name, normalize_date
from config import LLM_MODEL, LLM_URL, OPENAI_API_KEY, OPENAI_MODEL

OPENAI_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"}
# --- Pick correct LLM backend ---
def pick_llm(model: str = None):
    """
    Return an LLM instance.
    - "openai" → OpenAI
    - otherwise → Ollama with given model
    """
    
    chosen = (model or LLM_MODEL).lower()

    if chosen in OPENAI_MODELS:
        #print("openAI Key: ", OPENAI_API_KEY, "Model: ", OPENAI_MODEL)
        return ChatOpenAI(
            model=OPENAI_MODEL,
            api_key=OPENAI_API_KEY,
            request_timeout=300
        )
        
    else:
        return OllamaLLM(
            model=model or LLM_MODEL,
            base_url=LLM_URL,
            request_timeout=300,
            options={"stream": False}
        )

def call_llm(prompt: str, model: str = None) -> str:
    """
    Call an LLM (Ollama via REST or OpenAI via LangChain).
    - Defaults to Ollama model set in env (e.g., mistral).
    - If model="openai", it will call OpenAI instead.
    """

    model_name = model or LLM_MODEL

    # ---- Case 1: OpenAI ----
    if model_name in OPENAI_MODELS:
        try:
            llm = pick_llm(model_name)  # reuse picker for consistency
            resp = llm.invoke(prompt)
            return resp.content.strip()
        except Exception as e:
            print(f"❌ OpenAI call failed: {e}")
            return "⚠️ OpenAI service unavailable."

    # ---- Case 2: Ollama (direct REST) ----
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
        print(f"❌ Ollama call failed: {e}")
        return "⚠️ Ollama service unavailable."
    
# --- Schema ---
class PolicyMetadata(BaseModel):
    policyholder_name: Optional[str] = None
    policy_number: Optional[str] = None
    insurance_provider: Optional[str] = None
    insured_person: Optional[List[str]] = None
    policy_type: Optional[str] = None
    coverage: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# --- Dummy ---
def return_dummy():
    return PolicyMetadata(
        policyholder_name="Karthick Mani",
        policy_number="AUTH12345",
        insurance_provider="Niva Bupa",
        insured_person=["Karthick Mani"],
        policy_type="Health Recharge",
        coverage=["Hospitalization up to INR 25,00,000 with deductible INR 5,00,000"],
        start_date="2025-08-03",
        end_date="2026-08-02"
    ).dict()


# --- Helpers ---
def _safe_normalize(result) -> dict:
    if isinstance(result, list):
        # take first item or merge — depending on your use case
        result = result[0] if result else {}

    return {
        "policyholder_name": clean_name(clean_value(result.get("policyholder_name"))),
        "policy_number": clean_value(result.get("policy_number")),
        "insurance_provider": clean_value(result.get("insurance_provider")),
        "insured_person": result.get("insured_person") or [],
        "policy_type": clean_value(result.get("policy_type")),
        "coverage": result.get("coverage") or [],
        "start_date": normalize_date(clean_value(result.get("start_date"))),
        "end_date": normalize_date(clean_value(result.get("end_date"))),
    }


# --- Extraction ---
def extract_policy_metadata(document: str, model: str = None) -> dict:
    parser = JsonOutputParser(pydantic_object=PolicyMetadata)
    llm = pick_llm(model)
    fixing_parser = OutputFixingParser.from_llm(parser=parser, llm=llm)

    prompt = """
You are an expert assistant for insurance policies.

Extract the following fields from the policy text below:

- policyholder_name: The main contract holder or applicant. Remove titles (Mr., Mrs., Dr., etc.).
- insured_person: A list of all covered individuals. 
  • In health policies: list dependents, family members, or covered persons.  
  • In motor policies: usually the vehicle owner (often the same as policyholder).  
  • If none are listed separately, return an empty list.
- policy_number: The official policy number.
- insurance_provider: The insurance company name.
- policy_type: Type of insurance (Health, Motor/Vehicle, Life, Travel, etc.).
- coverage: A list of coverage items explicitly mentioned (hospitalization, accident, theft, third-party liability, etc.).
- start_date: Start date of the policy or "Period of Insurance".
- end_date: End/expiry date of the policy or "Period of Insurance".
- policy_issuer: The issuing office/branch/company details if listed.

STRICT MERGE RULES:
- If ANY chunk has a non-null value for a field, always keep that value in the final result.
- For start_date and end_date: never output null if at least one chunk provides a value.
- For lists (insured_person, coverage): merge across all chunks, deduplicate.
- For scalars (policyholder_name, policy_number, insurance_provider, policy_type, policy_issuer):
  * Prefer the most complete, non-null value.
  * Never replace a valid value with null.
- Final output must be ONE valid JSON object, no lists, no markdown, no comments.

{format_instructions}

Policy text:
{document}
"""

    print("Documents for extraction: ", document)

    chain = (
        PromptTemplate(
            template=prompt,
            input_variables=["document"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )
        | llm
        | fixing_parser
    )

    try:
        raw = chain.invoke({"document": document})
        print("RAW: ", raw)
        return _safe_normalize(raw)
    except Exception as e:
        print("❌ Metadata extraction failed:", e)
        return PolicyMetadata().dict()


# --- Merge ---
def extract_merged_policy_data(chunk_results: List[Dict], model: str = None) -> dict:
    parser = JsonOutputParser(pydantic_object=PolicyMetadata)
    llm = pick_llm(model)
    fixing_parser = OutputFixingParser.from_llm(parser=parser, llm=llm)

    merge_prompt = """
    You are an expert assistant for insurance policies.

    Your task is to MERGE the partial extraction results into ONE final JSON object.

    Schema:
    {format_instructions}

    Partial results:
    {chunk_results}

    STRICT MERGE RULES:
    - If ANY chunk result has a non-null, non-empty value for a field, use that value in the final JSON.
    - For start_date and end_date, always choose the non-null values if present. Do not output null if at least one chunk has them.
    - For lists (insured_person, coverage), merge and deduplicate across all partial results.
    - For scalar fields (policy_number, policyholder_name, insurance_provider, policy_type, policy_issuer), pick the longest non-null value if multiple exist.
    - Never drop correct values in favor of null.
    - For scalar fields (policyholder_name, policy_number, insurance_provider, policy_type, start_date, end_date, policy_issuer):
      • If multiple values exist, pick the most complete (non-null, non-empty, longer string).
      • If only one is non-null, use that.
    - Do not output null if at least one valid value exists.
    - Final output must be ONE valid JSON object only.
    """

    chain = (
        PromptTemplate(
            template=merge_prompt,
            input_variables=["chunk_results"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )
        | llm
        | fixing_parser
    )

    try:
        raw = chain.invoke({"chunk_results": str(chunk_results)})
        print("RAW MERGE OUTPUT:", raw)
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
    Insurance Provider: {insurance_provider}
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
            "insurance_provider",
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