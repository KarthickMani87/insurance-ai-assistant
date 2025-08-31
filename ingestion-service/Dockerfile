FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PyTorch, pdfplumber, etc.
RUN apt-get update && apt-get install -y \
    build-essential \
    libpoppler-cpp-dev \
    pkg-config \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install python deps
# Torch must be pinned from PyTorch wheels repo
RUN pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "worker.py"]
