from fastapi import FastAPI, UploadFile, Form
from typing import List
import shutil, os

app = FastAPI()

@app.post("/upload")
async def upload(files: List[UploadFile], policy_number: str = Form(...)):
    os.makedirs(f"/data/{policy_number}", exist_ok=True)
    for file in files:
        path = f"/data/{policy_number}/{file.filename}"
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    # Trigger ingestion...
    return {"status": "uploaded", "policy_number": policy_number}

@app.post("/query")
async def query(payload: dict):
    policy_number = payload["policy_number"]
    # Call LangGraph flow: retrieve docs + summarize
    result = {
        "policy_number": policy_number,
        "extracted": {
            "customer_name": "John Doe",
            "claim_amount": "50,000",
            "hospital": "City Hospital",
            "date": "2025-08-20"
        },
        "summary": "Claim for hospitalization under policy P1234.",
        "decision": "Approval likely",
        "fraud_flag": False
    }
    return result

