#!/bin/bash
set -eo pipefail

TEMPORAL_ADDRESS="${TEMPORAL_ADDRESS:-127.0.0.1:7233}"

echo "[temporal-ui] Waiting for temporal-server at ${TEMPORAL_ADDRESS}..."
until temporal operator cluster health --address "${TEMPORAL_ADDRESS}" 2>/dev/null | grep -q "SERVING"; do
    sleep 1
done
echo "[temporal-ui] temporal-server is SERVING, starting ui-server..."

exec temporal-ui-server \
    --root /etc/temporal \
    --config config \
    --env docker-ui \
    start
