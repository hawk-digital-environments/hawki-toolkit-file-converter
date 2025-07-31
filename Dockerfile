FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
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
    libc-bin \
    && rm -rf /var/lib/apt/lists/*

# Install pip dependencies
RUN pip install --no-cache-dir \
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
