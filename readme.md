# PDF Text Extraction API with PyMuPDF and FastAPI

This project provides a lightweight, containerized API for extracting and cleaning text from PDF files using [`PyMuPDF`](https://pymupdf.readthedocs.io/) and serving it with FastAPI.

##  Current Features

- Upload PDFs via an HTTP endpoint and get back cleaned text
- Dockerized setup

---

### 1. Build & Run (Dockerized)

```bash
./run.sh
```
This will build the Docker image (`pymupdf-extract`)

##  API Endpoint

Example using `curl`:

```bash
curl -X POST http://localhost:8001/extract \
  -H "Authorization: Bearer Your-secret-api-key" \
  -F "file=@/path/to/your/document.pdf"
  --output [Filename].zip
```

### Important Update> always use double qoutation around the "file=@/path/file.pdf"

### 2. Run in Production (Dockerized)

We provide a docker image at the docker hub: [digitalenvironments/hawki-toolkit-file-converter](https://hub.docker.com/r/digitalenvironments/hawki-toolkit-file-converter),
which can be run as follows:

```bash
docker run --rm -d -p 8001:8001 -e F_API_KEY="Your-secret-api-key" digitalenvironments/hawki-toolkit-file-converter:latest
```

Alternatively you can create a docker-compose file:

```yaml
services:
  file-converter:
    image: digitalenvironments/hawki-toolkit-file-converter:latest
    ports:
      - "8001:8001"
    environment:
      - F_API_KEY=Your-secret-api-key
    restart: unless-stopped
    healthcheck:
      # /health is public; no auth header needed for the check
      test: [ "CMD", "curl", "-f", "http://localhost:8001/health" ]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```
