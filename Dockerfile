FROM python:3.10-slim

LABEL org.opencontainers.image.authors="HAWKI Team <ki@hawk.de>"
LABEL org.opencontainers.image.description="The HAWKI file conversion service"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN --mount=type=cache,id=apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lib,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y \
    pandoc \
    tesseract-ocr \
    tesseract-ocr-deu \
    tesseract-ocr-eng \
    tesseract-ocr-fra \
    tesseract-ocr-ita \
    tesseract-ocr-spa \
    tesseract-ocr-nld \
    poppler-utils \
    curl \
    gcc \
    libgl1 \
    libc-bin

# Install pip dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-multipart \
    pymupdf \
    pypandoc \
    pytesseract \
    pdf2image \
    pillow \
    langdetect

# Copy the application files into the container
COPY main.py .
COPY utils/ utils/

# Expose FastAPI default port
EXPOSE 8001
ENV PYTHONUNBUFFERED=1

# FastAPI Server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "debug"]
