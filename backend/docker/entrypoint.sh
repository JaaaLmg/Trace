#!/bin/sh
set -eu

wait_for_db() {
  echo "Waiting for PostgreSQL..."
  for attempt in $(seq 1 60); do
    if python - <<'PY'
import os
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["TRACE_DB_URL"], pool_pre_ping=True)
with engine.connect() as connection:
    connection.execute(text("select 1"))
PY
    then
      echo "PostgreSQL is ready."
      return 0
    fi
    echo "PostgreSQL not ready yet (${attempt}/60)."
    sleep 2
  done
  echo "PostgreSQL did not become ready in time." >&2
  return 1
}

wait_for_redis() {
  echo "Waiting for Redis..."
  for attempt in $(seq 1 60); do
    if python - <<'PY'
import os
import redis

client = redis.Redis.from_url(os.environ["TRACE_REDIS_URL"])
client.ping()
PY
    then
      echo "Redis is ready."
      return 0
    fi
    echo "Redis not ready yet (${attempt}/60)."
    sleep 2
  done
  echo "Redis did not become ready in time." >&2
  return 1
}

run_bootstrap() {
  python scripts/init_db.py
  python scripts/seed_strategies.py
  python scripts/seed_eval_demo.py
}

case "${1:-api}" in
  api)
    wait_for_db
    wait_for_redis
    run_bootstrap
    exec python scripts/run_api.py
    ;;
  worker)
    wait_for_db
    wait_for_redis
    exec python scripts/run_worker.py
    ;;
  migrate)
    wait_for_db
    run_bootstrap
    ;;
  *)
    exec "$@"
    ;;
esac
