#!/bin/bash
set -e

if [ "${POSTGRES_ENABLED:-true}" = "true" ]; then
    echo "[prefect-server] Waiting for PostgreSQL to be ready..."
    until pg_isready -h 127.0.0.1 -p 5432 -q; do
        sleep 1
    done
    echo "[prefect-server] PostgreSQL is ready."
fi

exec prefect server start --host 0.0.0.0
