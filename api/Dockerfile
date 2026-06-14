# Build context is the repo root (see docker-compose.yml: context: .).
FROM python:3.12-slim

WORKDIR /app

# Cache HF weights inside the image at a fixed location so the pre-baked model
# below is shipped in the image rather than downloaded on first request.
ENV HF_HOME=/opt/hf-cache \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-bake the embedding model (~2 GB) into the image. Without this, the first
# query would trigger a Hugging Face download and cause slow/failed cold starts.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-large')"

COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8000

CMD ["uvicorn", "lawboi.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
