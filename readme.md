# PDF Text Extraction API with PyMuPDF and FastAPI

This project provides a lightweight, containerized API for extracting and cleaning text from PDF files using [`PyMuPDF`](https://pymupdf.readthedocs.io/) and serving it with FastAPI.

##  Current Features

- Upload PDFs via an HTTP endpoint and get back cleaned text
- Dockerized setup

---

### 1. Build & Run (Dockerized)

```bash
./run.sh

>>>> This will build the Docker image (`pymupdf-extract`)

##  API Endpoint

Example using `curl`:

```bash
curl -X POST http://localhost:8000/extract-pdf \
  -F "file=@/path/to/your/document.pdf"
```
