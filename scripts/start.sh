#!/usr/bin/env sh
# Container entrypoint: bring the database up to date, seed it if it's empty,
# then serve. Exits non-zero (and the deploy fails loudly) if the migration fails.
set -e

echo "==> alembic upgrade head"
alembic upgrade head

# This container serves a shared public demo, so it resets the demo data every hour
# (DEMO_RESET_SCHEDULE=nightly makes it once a day instead)
# (app/services/demo_reset.py) and on every start, which also covers a restart that
# happened to miss a scheduled run. Set DEMO_RESET_NIGHTLY=false to keep data as it is.
export DEMO_RESET_NIGHTLY="${DEMO_RESET_NIGHTLY:-true}"

if [ "${SEED_ON_DEPLOY:-true}" = "true" ]; then
  if [ "$DEMO_RESET_NIGHTLY" = "true" ]; then
    echo "==> resetting demo data"
    python scripts/seed.py
  else
    echo "==> seeding demo data (only if the database is empty)"
    python scripts/seed.py --if-empty
  fi
fi

echo "==> starting uvicorn on port ${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
