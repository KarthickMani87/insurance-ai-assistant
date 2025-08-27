from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from app.services import s3_service

router = APIRouter()

class FileRequest(BaseModel):
    filename: str
    content_type: str

class DeleteRequest(BaseModel):
    key: str

@router.post("/generate_presigned_url")
def generate_presigned_url(data: FileRequest):
    try:
        return s3_service.generate_presigned_url(data.filename, data.content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list_files")
def list_files():
    try:
        return {"files": s3_service.list_files()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete_file")
def delete_file(req: DeleteRequest = Body(...)):
    try:
        return s3_service.delete_file(req.key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

