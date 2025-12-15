#!/bin/bash

set -e

echo  "Building Docker image..."
docker build -t pymupdf-extract .

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

if [ -z "${F_API_KEY:-}" ]; then
  echo "F_API_KEY not set. Provide it in .env or export it before running." >&2
  exit 1
fi

echo "Running FastAPI container on http://localhost:8001 ..."
docker run --rm -p 8001:8001 -e "F_API_KEY=${F_API_KEY}" pymupdf-extract
