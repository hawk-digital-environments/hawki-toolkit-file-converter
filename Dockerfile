FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install pip dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-multipart \
    pymupdf

# Copy the FastAPI app script into the container
COPY process_pdfs.py .

# Expose FastAPI default port
EXPOSE 8000
ENV PYTHONUNBUFFERED=1
# FastAPI Server
CMD ["uvicorn", "process_pdfs:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "debug"]
