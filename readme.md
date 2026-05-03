# PDF Text Extraction API with PyMuPDF and FastAPI

This project provides a lightweight, containerized API for extracting and cleaning text from PDF files using [`PyMuPDF`](https://pymupdf.readthedocs.io/) and serving it with FastAPI.

##  Current Features

- Upload PDFs via an HTTP endpoint and get back cleaned text
- Dockerized setup based on Python 3.14 and FastAPI [with feature rich base image](https://github.com/Neunerlei/docker-images/blob/main/docs/python-nginx.md)

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

### Important Update> always use double quotation around the "file=@/path/file.pdf"

### 2. Run in Production (Dockerized)

We provide a docker image at the docker hub: [digitalenvironments/hawki-toolkit-file-converter](https://hub.docker.com/r/digitalenvironments/hawki-toolkit-file-converter),
which can be run as follows:

```bash
docker run --rm -d -p 8001:80 -e F_API_KEY="Your-secret-api-key" digitalenvironments/hawki-toolkit-file-converter:latest
```

Alternatively you can create a docker-compose file:

```yaml
services:
  file-converter:
    image: digitalenvironments/hawki-toolkit-file-converter:latest
    ports:
      - "8001:80"
    environment:
      - F_API_KEY=Your-secret-api-key
    restart: unless-stopped
```

### 3. Running with a local HAWKI instance

If you want to run with a local HAWKI instance, you can copy the `docker-compose.local.yml` file to `docker-compose.override.yml` and start the environment with `docker compose up`. Ensure the hawki instance is running and the API key in the `.env` file matches the one on the HAWKI side. We are simply reusing the `hawki_hawk_net` network that is already created by the HAWKI environment, so no additional network configuration is needed.

## RabbitMQ Worker Extension

The service now supports an additive worker mode for pipeline events, without changing the existing HTTP converter API behavior.

Flow:

- scraper publishes `scrape.file.discovered` to `pipeline.events`
- file-converter worker consumes and converts
- file-converter publishes `convert.document.completed` to `pipeline.events`
- if conversion fails permanently, worker publishes `pipeline.failed` to `pipeline.failed`

### Environment Variables

Use `.env.example` for the complete list. Worker-related variables:

```env
COMMUNICATION_ENABLED=true
COMMUNICATION_METHOD=rabbitmq

RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_VHOST=/
RABBITMQ_HEARTBEAT=30
RABBITMQ_CONNECTION_TIMEOUT=30

RABBITMQ_EVENTS_EXCHANGE=pipeline.events
RABBITMQ_EVENTS_EXCHANGE_TYPE=direct
RABBITMQ_RETRY_EXCHANGE=pipeline.retry
RABBITMQ_RETRY_EXCHANGE_TYPE=direct
RABBITMQ_FAILED_EXCHANGE=pipeline.failed
RABBITMQ_FAILED_EXCHANGE_TYPE=direct

RABBITMQ_FILE_CONVERSION_QUEUE=file_conversion_jobs
RABBITMQ_FILE_DISCOVERED_ROUTING_KEY=scrape.file.discovered
RABBITMQ_FILE_CONVERSION_RETRY_QUEUE=file_conversion_jobs_retry
RABBITMQ_FILE_CONVERSION_RETRY_ROUTING_KEY=scrape.file.discovered.retry
RABBITMQ_DOCUMENT_CONVERTED_ROUTING_KEY=convert.document.completed

RABBITMQ_FAILED_QUEUE=failed_jobs
RABBITMQ_FAILED_ROUTING_KEY=pipeline.failed

RABBITMQ_RETRY_DELAY_MS=5000
RABBITMQ_PREFETCH_COUNT=1
RABBITMQ_MAX_RETRIES=3
RABBITMQ_QUEUE_TYPE=quorum

RABBITMQ_PUBLISHER_CONFIRMS=true
RABBITMQ_PERSISTENT_MESSAGES=true

JOB_SCHEMA_VERSION=1
SERVICE_NAME=file-converter

SHARED_STORAGE_ROOT=/app/shared
CONVERTED_OUTPUT_ROOT=/app/shared/converted
```

### Run Worker

Local Python:

```bash
python -m workers.file_conversion_worker
```

Docker Compose profile:

```bash
docker compose --profile worker up -d file-converter-worker
```

### Expected Input Event (`scrape.file.discovered`)

```json
{
  "event_id": "2d486569-a423-4fbd-8d5a-b4cf41dbe55a",
  "job_id": "6f14613f-a7f0-41b7-b9f6-f56cb62e3e4b",
  "schema_version": "1",
  "event_type": "scrape.file.discovered",
  "source": "scraper",
  "url": "https://example.com/file.pdf",
  "page_url": "https://example.com",
  "local_path": "/app/shared/input/file.pdf",
  "relative_path": "input/file.pdf",
  "filename": "file.pdf",
  "extension": ".pdf",
  "content_type": "application/pdf",
  "file_size_bytes": 1024,
  "checksum_sha256": "optional-input-checksum",
  "discovered_at": "2026-04-27T12:00:00Z",
  "trace_id": "trace-123",
  "payload": {}
}
```

### Expected Output Event (`convert.document.completed`)

```json
{
  "event_id": "f2df71c2-c8d3-447d-b4be-f95c82d88e48",
  "job_id": "6f14613f-a7f0-41b7-b9f6-f56cb62e3e4b",
  "parent_event_id": "2d486569-a423-4fbd-8d5a-b4cf41dbe55a",
  "schema_version": "1",
  "event_type": "convert.document.completed",
  "source": "file-converter",
  "original_url": "https://example.com/file.pdf",
  "original_path": "/app/shared/input/file.pdf",
  "original_relative_path": "input/file.pdf",
  "converted_path": "/app/shared/converted/6f14613f-a7f0-41b7-b9f6-f56cb62e3e4b/input/file.md",
  "converted_relative_path": "6f14613f-a7f0-41b7-b9f6-f56cb62e3e4b/input/file.md",
  "output_format": "markdown",
  "converter_name": "file-converter",
  "converter_version": null,
  "input_checksum_sha256": "sha256-input",
  "output_checksum_sha256": "sha256-output",
  "converted_at": "2026-04-27T12:00:05Z",
  "trace_id": "trace-123",
  "payload": {
    "duplicate": false
  }
}
```

### Retry and Failed Behavior

- Consumer queue: `file_conversion_jobs`
- Retry queue: `file_conversion_jobs_retry` with TTL and DLX back to `pipeline.events` + `scrape.file.discovered`
- Failed queue: `failed_jobs` bound to `pipeline.failed`
- Worker uses manual ACK and only ACKs after:
  - success publish of `convert.document.completed`, or
  - success publish to retry exchange, or
  - success publish of `pipeline.failed`

No infinite nack/requeue loop is used.
