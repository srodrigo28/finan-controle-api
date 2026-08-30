#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS_ON_STARTUP:-0}" = "1" ]; then
  echo "[entrypoint] aplicando migrações..."
  flask --app run.py db upgrade
fi

exec "$@"
