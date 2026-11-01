# croScan web server: FastAPI + 한컴 OpenDataLoader (bundled jar, needs a Java runtime)
# Build:  docker build --platform linux/amd64 -t croscan .
# Run:    docker run --rm -p 8765:8765 croscan        -> http://localhost:8765
# PORT sets the listening port (cloud platforms often pass it); default 8765.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8 \
    PORT=8765

# OpenDataLoader runs `java -jar ...`; a headless JRE 17 is enough.
# NanumGothic draws the 추가검토서 (page 2) in Korean.
RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jre-headless fonts-nanum \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY server ./server
COPY web ./web

# run as a normal user; /tmp holds the uploaded PDF and OpenDataLoader's output while a request runs.
# /app/data keeps the QA reports (mount a volume there so they survive a rebuild)
RUN useradd --create-home --uid 10001 croscan && mkdir -p /app/data && chown -R croscan /app
USER croscan

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8765\")}/api/health', timeout=4)"
CMD ["sh", "-c", "exec uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8765}"]
