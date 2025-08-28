import boto3
import re
from datetime import datetime, timezone
from app import config
from botocore.client import Config

s3_client = boto3.client(
    "s3",
    aws_access_key_id=config.AWS_ACCESS_KEY,
    aws_secret_access_key=config.AWS_SECRET_KEY,
    region_name=config.AWS_REGION,
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
)

def generate_presigned_url(filename: str, content_type: str, expires_in: int = 3600):
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
    #key = f"uploads/{datetime.now(timezone.utc).isoformat()}_{clean_name}"
    key = f"uploads/{clean_name}"


    print("DEBUG >>> AWS_REGION from config:", config.AWS_REGION)

    url = s3_client.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": config.S3_BUCKET,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in
    )
    return {"url": url, "key": key}

def list_files(prefix="uploads/"):
    response = s3_client.list_objects_v2(Bucket=config.S3_BUCKET, Prefix=prefix)
    contents = response.get("Contents", [])
    return [obj["Key"] for obj in contents]

def delete_file(key: str):
    s3_client.delete_object(Bucket=config.S3_BUCKET, Key=key)
    return {"message": f"Deleted {key}"}

