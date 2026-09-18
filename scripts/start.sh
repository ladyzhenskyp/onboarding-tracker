#!/usr/bin/env sh
# Container entrypoint: bring the database up to date, seed it if it's empty,
# then serve. Exits non-zero (and the deploy fails loudly) if the migration fails.
set -e

echo "==> alembic upgrade head"
alembic upgrade head

if [ "${SEED_ON_DEPLOY:-true}" = "true" ]; then
  echo "==> seeding demo data (only if the database is empty)"
  python scripts/seed.py --if-empty
fi

echo "==> starting uvicorn on port ${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
