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

## Development

### Tests
To run tests use `docker compose -f docker-compose.ci.yml up --build`
=======
### Devcontainer
Using a [devcontainer](https://containers.dev/implementors/json_reference/) in this project has the advantage that required system libraries like tesserract do not have to be installed on the local system.
Also all python development tools like do not have to be installed on the local machine.

### Debugging
Existing debug setups:
 - vscode (see .vscode/launch.json)
 - start a fasapi development server via `uv run dev` 

### Tests
To run tests use `docker compose -f docker-compose.ci.yml up --build`

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
}
```
Run `cargo run` and extract file extensions with your favorite llm.
