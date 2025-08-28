import os
from dotenv import load_dotenv

# Load .env only if it exists (dev/local)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
S3_BUCKET = os.getenv("S3_BUCKET")
