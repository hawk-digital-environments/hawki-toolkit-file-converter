FROM neunerlei/python-nginx:3.14 as deployment

LABEL org.opencontainers.image.authors="HAWKI Team <ki@hawk.de>"
LABEL org.opencontainers.image.description="The HAWKI file conversion service"

ENV PYTHONUNBUFFERED=1
# Configure the base image to run the FastAPI app with Gunicorn and Uvicorn workers
# See: https://github.com/Neunerlei/docker-images/blob/main/docs/python-nginx.md#configuration-via-environment-variables
ENV PYTHON_APP_MODULE="main:app"
ENV GUNICORN_WORKER_CLASS="uvicorn.workers.UvicornWorker"

# Install system dependencies
RUN --mount=type=cache,id=apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lib,target=/var/lib/apt,sharing=locked \
    apt update && apt install -y \
    pandoc \
    tesseract-ocr \
    tesseract-ocr-deu \
    tesseract-ocr-eng \
    tesseract-ocr-fra \
    tesseract-ocr-ita \
    tesseract-ocr-spa \
    tesseract-ocr-nld \
    poppler-utils \
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

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

FROM deployment as test

COPY ./tests ./tests
COPY pytest.ini .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    pytest \
    httpx

FROM deployment