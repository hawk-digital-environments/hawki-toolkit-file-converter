# RabbitMQ Pipeline Flow

This file converter can run as a RabbitMQ worker in the HAWKI pipeline. In that mode, the HTTP API is not the main integration point. Instead, services communicate through RabbitMQ events and shared storage.

## Main Flow

```text
scraper
  -> publishes scrape.file.discovered to RabbitMQ

RabbitMQ
  -> routes message into file_conversion_jobs

file-converter-worker
  -> consumes file_conversion_jobs
  -> converts the file to Markdown
  -> writes output into shared storage
  -> publishes convert.document.completed back to RabbitMQ

hawki-rag
  -> consumes convert.document.completed
  -> picks up the converted Markdown
  -> continues ingestion/indexing
```

## What The Worker Expects

The worker expects the scraper to publish a `scrape.file.discovered` event to the `pipeline.events` exchange with the routing key `scrape.file.discovered`.

RabbitMQ routes that event into the `file_conversion_jobs` queue. The `file-converter-worker` consumes from this queue.

The event must include enough file information for the worker to find the original file in shared storage, especially:

- `local_path`
- `relative_path`
- `filename`
- `extension`
- `job_id`
- `event_id`

The worker validates the path, reads the file from shared storage, converts supported files to Markdown, and writes the converted output under the configured converted output directory.

Supported input formats (for now!!):

- `.pdf`
- `.doc`
- `.docx`

## What The Worker Publishes

After a successful conversion, the worker publishes a `convert.document.completed` event back to RabbitMQ.

Default exchange:

```text
pipeline.events
```

Default routing key:

```text
convert.document.completed
```

HAWKI-RAG then consumes this event, reads the converted Markdown file from shared storage, and continues ingestion/indexing.

## Required Runtime Setup

The worker is behind the Docker Compose `worker` profile. It is not started by plain `docker compose up -d`.

Start it with:

```bash
docker compose --profile worker up -d
```

If RabbitMQ is provided by the larger HAWKI/RAG stack on the external `hawki-network`, use the local override too:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml --profile worker up -d
```

The worker must be connected to the same RabbitMQ instance and shared storage as the scraper and HAWKI-RAG.

## Default RabbitMQ Names

```text
Input exchange:        pipeline.events
Input routing key:    scrape.file.discovered
Input queue:          file_conversion_jobs

Output exchange:       pipeline.events
Output routing key:   convert.document.completed

Retry exchange:        pipeline.retry
Retry queue:           file_conversion_jobs_retry
Failed exchange:       pipeline.failed
Failed queue:          failed_jobs
```

## Failure And Retry Flow

If the worker has a transient failure, it republishes the message to the retry exchange:

```text
pipeline.retry
```

RabbitMQ holds the message in the retry queue for the configured delay, then dead-letters it back to the normal input exchange and routing key.

If the worker reaches the max retry count or detects a permanent failure, it publishes a `pipeline.failed` event to:

```text
pipeline.failed
```

