#!/bin/bash
set -eo pipefail

TEMPORAL_HOME="${TEMPORAL_HOME:-/etc/temporal}"
SCHEMA_DIR="${TEMPORAL_HOME}/schema/postgresql/v12"
POSTGRES_SEEDS="${POSTGRES_SEEDS:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-temporal}"
POSTGRES_PWD="${POSTGRES_PWD:-}"
DBNAME="${DBNAME:-temporal}"
VISIBILITY_DBNAME="${VISIBILITY_DBNAME:-temporal_visibility}"
DEFAULT_NAMESPACE="${DEFAULT_NAMESPACE:-default}"
DEFAULT_NAMESPACE_RETENTION="${DEFAULT_NAMESPACE_RETENTION:-24h}"

echo "[temporal-server] temporal-server version: $(temporal-server --version 2>&1)"
echo "[temporal-server] temporal-sql-tool version: $(temporal-sql-tool --version 2>&1)"

if [ "${POSTGRES_ENABLED:-true}" = "true" ]; then
    echo "[temporal-server] Waiting for PostgreSQL to be ready..."
    until pg_isready -h "${POSTGRES_SEEDS}" -p "${DB_PORT}" -q; do
        sleep 1
    done
    echo "[temporal-server] PostgreSQL is ready."
fi

export SQL_PASSWORD="${POSTGRES_PWD}"

echo "[temporal-server] Setting up PostgreSQL schema (idempotent)..."

# Databases are pre-created in the Dockerfile (createdb -O temporal temporal).
# Only set up the schema and apply migrations.

temporal-sql-tool \
    --plugin postgres12 \
    --ep "${POSTGRES_SEEDS}" \
    -u "${POSTGRES_USER}" \
    -p "${DB_PORT}" \
    --db "${DBNAME}" \
    --tls=false \
    setup-schema -v 0.0

temporal-sql-tool \
    --plugin postgres12 \
    --ep "${POSTGRES_SEEDS}" \
    -u "${POSTGRES_USER}" \
    -p "${DB_PORT}" \
    --db "${DBNAME}" \
    --tls=false \
    update-schema -d "${SCHEMA_DIR}/temporal/versioned"

temporal-sql-tool \
    --plugin postgres12 \
    --ep "${POSTGRES_SEEDS}" \
    -u "${POSTGRES_USER}" \
    -p "${DB_PORT}" \
    --db "${VISIBILITY_DBNAME}" \
    --tls=false \
    setup-schema -v 0.0

temporal-sql-tool \
    --plugin postgres12 \
    --ep "${POSTGRES_SEEDS}" \
    -u "${POSTGRES_USER}" \
    -p "${DB_PORT}" \
    --db "${VISIBILITY_DBNAME}" \
    --tls=false \
    update-schema -d "${SCHEMA_DIR}/visibility/versioned"

# Resolve bind IP / broadcast address like the official entrypoint
: "${BIND_ON_IP:=$(getent hosts "$(hostname)" | awk '{print $1;}')}"
export BIND_ON_IP

if [ "${BIND_ON_IP}" = "0.0.0.0" ] || [ "${BIND_ON_IP}" = "::0" ]; then
    : "${TEMPORAL_BROADCAST_ADDRESS:=$(getent hosts "$(hostname)" | awk '{print $1;}')}"
    export TEMPORAL_BROADCAST_ADDRESS
fi

echo "[temporal-server] Starting temporal-server (BIND_ON_IP=${BIND_ON_IP})..."
cd "${TEMPORAL_HOME}"
temporal-server --env docker start &
SERVER_PID=$!

TEMPORAL_CLI_ADDR="${POSTGRES_SEEDS}:7233"
echo "[temporal-server] Waiting for temporal-server to be SERVING..."
until temporal operator cluster health --address "${TEMPORAL_CLI_ADDR}" 2>/dev/null | grep -q "SERVING"; do
    sleep 1
done
echo "[temporal-server] Server is SERVING."

if ! temporal operator namespace describe \
    --address "${TEMPORAL_CLI_ADDR}" \
    --namespace "${DEFAULT_NAMESPACE}" >/dev/null 2>&1; then
    echo "[temporal-server] Registering default namespace: ${DEFAULT_NAMESPACE}"
    temporal operator namespace create \
        --address "${TEMPORAL_CLI_ADDR}" \
        --retention "${DEFAULT_NAMESPACE_RETENTION}" \
        --namespace "${DEFAULT_NAMESPACE}"
else
    echo "[temporal-server] Default namespace already registered."
fi

wait "${SERVER_PID}"
