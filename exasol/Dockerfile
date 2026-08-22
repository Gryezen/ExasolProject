# Container image for the Agentic Document Intelligence Platform.
#
# Built for Render.com (see render.yaml) but works on any container host.
# Uses a real Dockerfile rather than Render's native Python build because
# pytesseract and pdf2image need OS packages (tesseract-ocr, poppler-utils)
# that Render's native buildpack build step cannot apt-get install.

FROM python:3.13-slim

# tesseract-ocr: OCR fallback for scanned PDFs / images (agents/ingestion.py)
# poppler-utils: gives pdf2image its `pdftoppm`/`pdftocairo` binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Uploaded files land here at runtime (see config.py's UPLOAD_DIR). On
# Render's free/starter tiers this directory is ephemeral — it's wiped on
# every redeploy/restart — which is fine for a demo but not for
# production persistence. Mount a Render Disk at this path if uploads
# need to survive restarts.
RUN mkdir -p /app/data/uploads

ENV PORT=10000
EXPOSE 10000

CMD ["sh", "-c", "gunicorn -w 2 -k gthread --threads 4 -b 0.0.0.0:${PORT} api.routes:app"]
