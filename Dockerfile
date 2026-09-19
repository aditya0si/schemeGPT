FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# CPU-only torch is installed from the official PyTorch CPU index before the
# rest of the API dependencies; see requirements-api.txt. Local dev on
# Windows/Python 3.12 keeps using requirements.txt unchanged.
COPY requirements-api.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

# Bake the default embedding model into the image so container starts are
# fast and do not depend on Hugging Face availability at runtime. Must match
# the EMBEDDING_MODEL setting (intfloat/multilingual-e5-small).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"

COPY app ./app
COPY data ./data

# Build identity: reported by GET /ops/status so a running container can be tied
# back to the commit it was built from. Placed last on purpose — changing the
# SHA must not invalidate the cached dependency/model layers above it.
ARG GIT_SHA=""
ENV GIT_SHA=${GIT_SHA}

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
