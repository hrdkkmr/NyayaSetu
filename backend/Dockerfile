FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Tesseract with Hindi + English packs enables OCR of scanned documents.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-hin tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-optional.txt ./
RUN pip install -r requirements.txt && pip install pytesseract

COPY . .
RUN useradd --create-home --uid 10001 nyayasetu && mkdir -p /app/var && chown -R nyayasetu /app/var
USER nyayasetu

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/ready').status==200 else 1)"

# Migrations run as a separate release step (see docker-compose.yml / DEPLOYMENT_GUIDE.md).
# Set FORWARDED_ALLOW_IPS to your load balancer/proxy addresses so client IPs cannot be spoofed.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]
