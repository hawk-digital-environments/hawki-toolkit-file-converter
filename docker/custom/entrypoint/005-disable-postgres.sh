#!/bin/bash
if [ "${POSTGRES_ENABLED:-true}" != "true" ]; then
    echo "[entrypoint] POSTGRES_ENABLED is not 'true', removing postgres supervisor config."
    rm -f /etc/supervisor/conf.d/10-postgres.conf
else
    mkdir -p /var/run/postgresql
    chown postgres:postgres /var/run/postgresql
fi
