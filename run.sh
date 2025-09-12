#!/bin/bash

set -e

echo  "Building Docker image..."
docker build -t pymupdf-extract .

echo "Running FastAPI container on http://localhost:8001 ..."
docker run --rm -p 8001:8001 pymupdf-extract