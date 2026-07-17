# PDF Text Extraction API with PyMuPDF and FastAPI

This project provides a lightweight, containerized API for extracting and cleaning text from PDF files using [`kreuzberg`](https://github.com/kreuzberg-dev/kreuzberg) and serving it with FastAPI.

##  Current Features

- Upload documents via an HTTP endpoint and get back cleaned text.
- Dockerized setup based on Python 3.14 and FastAPI [with feature rich base image](https://github.com/Neunerlei/docker-images/blob/main/docs/python-nginx.md).
- The default language for OCR is "de". This can be changed via the env `OCR_LANGUAGES` and only affects documents where language detection fails. Allowed is a comma seperated list of languages, but each added language increases runtime.
- The number of characters per chunked document is adjustable. The default `MAX_CHUNK_LENGTH` is 3000 and is a soft limit. E.g. a single number with more than 3000 digits will not be split to multiple documents.
- Then default number of keywords for each detected language is 10. It can be adjusted via `MAX_KEYWORDS_FOR_LANGUAGE`
- Async conversion pipeline (`POST /convert`, `GET /download/{job_id}`, `GET /jobs`, `GET /jobs/{job_id}`) with content-hash dedup, callback URLs, and Temporal Schedule-driven TTL cleanup.
---

### Job lifetime & retention

Two independent timers govern how long a `/convert` job stays accessible. They must be configured together:

| Timer | Where | Default | What it controls |
|---|---|---|---|
| `DEFAULT_NAMESPACE_RETENTION` | Temporal server (`Dockerfile`) | 24h | How long the workflow **record** remains queryable by `/download`, `/jobs`, `/jobs/{job_id}` |
| `ZIP_TTL_HOURS` | App (cleanup Schedule) | 24h | How long the **result zip** remains on disk under `SHARED_TMP` |

**Constraint: keep `ZIP_TTL_HOURS <= DEFAULT_NAMESPACE_RETENTION`.**

The download and job-status endpoints query Temporal for the workflow record first. Once retention purges the workflow:
- `/download/{job_id}` returns `404 job_not_found`
- `/jobs/{job_id}` returns `404 job_not_found`
- `/jobs` no longer lists the job

…even if the zip file is still on disk. Setting `ZIP_TTL_HOURS > DEFAULT_NAMESPACE_RETENTION` produces a window where the zip exists but is unreachable. After both timers expire, the job is fully gone and the caller must `POST /convert` again.

The TTL is renewed on every `/download`, so an actively downloaded zip effectively never expires (within retention bounds).

### 1. Build & Run (Dockerized)

```bash
make run
```
This will build the Docker image (`digitalenvironments/hawki-toolkit-file-converter:local`) and start the container on `http://localhost:8001`. Requires a `.env` file with `F_API_KEY` set.

##  API Endpoint

Example using `curl`:

```bash
curl -X POST http://localhost:8003/extract \
-H "Authorization: Bearer 123" \
-F "file=@/home/slave/Downloads/footable.xlsx" \
--output [Filename].zip
```

### Important Update> always use double quotation around the "file=@/path/file.pdf"

### 2. Deployment

The container runs PostgreSQL, Temporal Server, Temporal UI, and a Temporal Worker under [supervisor](http://supervisord.org/). All Temporal state (workflow history, namespaces) is stored in PostgreSQL inside the container.

#### Persistence

By default, PostgreSQL data lives inside the container and is **lost when the container is removed**. To persist data across container recreation (updates, host reboots), mount a named volume at `/var/lib/postgresql/17/main`:

**docker-compose:**
```yaml
services:
  file-converter:
    image: digitalenvironments/hawki-toolkit-file-converter:latest
    ports:
      - "8001:80"
    environment:
      - F_API_KEY=Your-secret-api-key
    volumes:
      - postgres_data:/var/lib/postgresql/17/main
    restart: unless-stopped

volumes:
  postgres_data:
```

**docker run:**
```bash
docker run -d \
  -p 8001:80 \
  -e F_API_KEY="Your-secret-api-key" \
  -v postgres_data:/var/lib/postgresql/17/main \
  --restart unless-stopped \
  digitalenvironments/hawki-toolkit-file-converter:latest
```

#### First-run initialization

On the first start with an empty volume, the container automatically:
1. Initializes the PostgreSQL data directory (`initdb`)
2. Creates the `temporal` role and `temporal` + `temporal_visibility` databases
3. Applies the Temporal PostgreSQL schema migrations
4. Registers the `default` namespace

Subsequent starts skip steps 1–2 (detecting existing data) and only run the idempotent schema check (step 3) and namespace check (step 4).

#### Backup & restore

Back up both databases:
```bash
docker exec <container> pg_dump -U temporal temporal > temporal-backup.sql
docker exec <container> pg_dump -U temporal temporal_visibility > visibility-backup.sql
```

Restore:
```bash
docker exec -i <container> psql -U temporal temporal < temporal-backup.sql
docker exec -i <container> psql -U temporal temporal_visibility < visibility-backup.sql
```

#### Upgrading

1. Back up both databases (see above)
2. Pull the new image
3. Restart the container — Temporal schema migrations are applied automatically on startup

### 3. Running with a local HAWKI instance

If you want to run with a local HAWKI instance, you can copy the `docker-compose.local.yml` file to `docker-compose.override.yml` and start the environment with `docker compose up`. Ensure the hawki instance is running and the API key in the `.env` file matches the one on the HAWKI side. We are simply reusing the `hawki_hawk_net` network that is already created by the HAWKI environment, so no additional network configuration is needed.

## Development

### Devcontainer
Using a [devcontainer](https://containers.dev/implementors/json_reference/) in this project has the advantage that required system libraries like tesserract do not have to be installed on the local system.
Also all python development tools like do not have to be installed on the local machine.

### Debugging
Existing debug setups:
 - vscode (see .vscode/launch.json)
 - start a fasapi development server via `uv run dev` 

### Tests
To run tests use `make ci-test`

### Extracting supported file formats
There is (currently) no interface to get supported file formats in python, so they are extracted statically.
Example extracting supported formats in Rust:
```
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo new kreuzberg_example
cd kreuzberg_example
cargo add kreuzberg
```
edit src/main.rs to contain:
```
use kreuzberg::core::mime::list_supported_formats;

fn main() {
    let formats = list_supported_formats();
    assert!(!formats.is_empty());
    assert!(formats.iter().any(|f| f.extension == "pdf"));

    println!("Supported formats:");
    for f in formats {
        println!("{} ({})", f.extension, f.mime_type);
    }
    for f in list_supported_formats() {
        println!("{}", f.extension);
    }
}
```
Run `cargo run` and extract file extensions.
