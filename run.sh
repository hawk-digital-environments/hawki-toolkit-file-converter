#!/bin/bash

set -e

echo  "Building Docker image..."
docker build -t pymupdf-extract .

echo "Running FastAPI container on http://localhost:8000 ..."
docker run --rm -p 8000:8000 pymupdf-extract