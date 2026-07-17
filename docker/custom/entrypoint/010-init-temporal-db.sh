#!/bin/bash
set -e

if [ "${POSTGRES_ENABLED:-true}" != "true" ]; then
    echo "[entrypoint] POSTGRES_ENABLED is not 'true', skipping PostgreSQL init."
    exit 0
fi

PGDATA="/var/lib/postgresql/17/main"
PG_BIN="/usr/lib/postgresql/17/bin"

# Step 1: Initialize data directory if needed (volume or first boot)
if [ -f "$PGDATA/PG_VERSION" ]; then
    echo "[entrypoint] PostgreSQL data directory already initialized."
else
    echo "[entrypoint] First run: initializing PostgreSQL data directory..."
    mkdir -p "$PGDATA"
    chown -R postgres:postgres "$PGDATA"
    chmod 700 "$PGDATA"
    su - postgres -c "$PG_BIN/initdb -D '$PGDATA' --auth-local=trust --auth-host=trust --username=postgres"
    echo "[entrypoint] PostgreSQL data directory initialized."
fi

# Step 2: Ensure temporal role and databases exist (always, idempotent)
echo "[entrypoint] Ensuring temporal role and databases exist..."
pg_ctlcluster 17 main start

if ! su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='temporal'\"" | grep -q 1; then
    su - postgres -c "createuser -s temporal"
    echo "[entrypoint] Created temporal role."
fi

for db in temporal temporal_visibility; do
    if ! su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='$db'\"" | grep -q 1; then
        su - postgres -c "createdb -O temporal $db"
        echo "[entrypoint] Created $db database."
    fi
done

pg_ctlcluster 17 main stop
echo "[entrypoint] Temporal role and databases ready."
