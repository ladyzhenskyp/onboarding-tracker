# Production image. Railway (and any Docker host) builds this on every push.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so this layer is cached between code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x scripts/start.sh

# Railway injects PORT; default for local docker run.
ENV PORT=8000
EXPOSE 8000

CMD ["scripts/start.sh"]
