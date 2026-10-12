# CyberBuddy Backend — FastAPI + Uvicorn
#
# Build context: ./backend
# The BGE embedding model (~1.3 GB) is downloaded at first runtime into
# $HF_HOME, which is a mounted volume so it survives container rebuilds.

FROM python:3.12-slim

WORKDIR /app

# System deps — curl for health checks; gcc/build-essential pulled in by
# wheels where needed (asyncpg, uvicorn[standard] ship wheels for slim).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cached layer) then copy app code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HuggingFace model cache lives outside the image (mounted volume)
ENV HF_HOME=/models/huggingface \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
