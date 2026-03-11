#!/bin/sh
set -eu

if [ -z "${MIND_POSTGRES_DSN:-}" ]; then
  echo "MIND_POSTGRES_DSN must be set" >&2
  exit 1
fi

if [ -z "${MIND_API_KEY:-}" ]; then
  echo "MIND_API_KEY must be set" >&2
  exit 1
fi

bind="${MIND_API_BIND:-0.0.0.0:8000}"
host="${bind%:*}"
port="${bind##*:}"
if [ "$host" = "$bind" ]; then
  host="0.0.0.0"
fi

alembic upgrade head

if [ "${MIND_DEV_MODE:-false}" = "true" ]; then
  echo "[entrypoint] DEV MODE: uvicorn --reload --log-level debug"
  exec uvicorn mind.api.app:create_app --factory --host "$host" --port "$port" \
    --reload --reload-dir /app/mind --log-level debug
else
  exec uvicorn mind.api.app:create_app --factory --host "$host" --port "$port"
fi
