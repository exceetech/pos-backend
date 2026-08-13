# Slim base image — has Python but not the full OS toolchain, so the
# image stays small. Version matches the local dev venv (python3.13) so
# behavior doesn't silently differ between your machine and the container.
FROM python:3.13-slim

# Don't write .pyc files (nothing benefits from them in a short-lived
# container) and don't buffer stdout/stderr — buffered output can make
# logs appear out of order or go missing on crash, which matters a lot
# when GCP is your only window into what happened.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies BEFORE copying the rest of the source. Docker
# caches each instruction as a layer — as long as requirements.txt
# doesn't change, this layer is reused on every rebuild instead of
# re-downloading every package, which is the single biggest thing that
# makes repeat builds fast.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual application code. .dockerignore controls what
# does NOT get copied here — see that file for what's excluded and why.
COPY . .

# Cloud Run injects the PORT environment variable at runtime and expects
# the container to listen on it — it is NOT always 8080, so the app
# must read $PORT rather than hardcoding it. gunicorn with uvicorn
# workers is the standard production combo for FastAPI: gunicorn manages
# worker processes (restarts a worker if it crashes), uvicorn's worker
# class handles the actual async request serving.
CMD ["sh", "-c", "gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 60"]
