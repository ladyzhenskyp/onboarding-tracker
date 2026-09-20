"""Scheduled demo reset (hourly or nightly).

The live site is a shared demo: every visitor signs in with the same account and
can advance stages, add blockers and so on. Left alone, the data drifts away from
the designed 4 red / 6 amber / 10 green story, and because health is computed
against today's date, every account slowly goes overdue.

So on a schedule (every hour on the hour, or once a night) the app wipes the demo
data and seeds it again, with all dates relative to the new "today". It is an
in-process background task rather than a
separate cron service: one less thing to configure on Railway, and the app only
ever runs as a single process there.

Off by default. scripts/start.sh switches it on in the container, so local
development (`uvicorn --reload`) never wipes your working data by surprise.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import settings

# uvicorn's own logger, so these lines show up in the server log (and in Railway's log view)
log = logging.getLogger("uvicorn.error")


def seconds_until_next_hour(now: datetime) -> float:
    """Seconds from `now` until the top of the next hour."""
    top = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return (top - now).total_seconds()


def seconds_until(hour_utc: int, now: datetime) -> float:
    """Seconds from `now` until the next time the clock reads `hour_utc`:00 UTC."""
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def reseed() -> None:
    """Wipe and re-seed in one transaction (see scripts/seed.py)."""
    from scripts import seed  # imported lazily: Faker is only needed when this runs

    seed.run()


def seconds_until_next_reset(now: datetime) -> float:
    if settings.demo_reset_schedule == "hourly":
        return seconds_until_next_hour(now)
    return seconds_until(settings.demo_reset_hour_utc, now)


def next_reset_at(now: datetime | None = None) -> datetime | None:
    """When the data will next be put back, or None if resets are off. Templates use this
    for the "Demo resets in N min" note and for the wording of "that item is gone"."""
    if not settings.demo_reset_nightly:
        return None
    now = now or datetime.now(timezone.utc)
    return now + timedelta(seconds=seconds_until_next_reset(now))


RETRIES = 3
RETRY_WAIT_SECONDS = 5


async def reseed_with_retry(wait: float = RETRY_WAIT_SECONDS) -> bool:
    """Run the reset, trying again if it fails.

    The reset locks every table for a moment. Very occasionally a visitor's request and the
    reset each end up waiting for a lock the other holds; Postgres breaks the tie by
    cancelling one of them. If the reset is the one cancelled, waiting a few seconds and
    trying again succeeds, which beats leaving the demo stale for another hour.
    """
    for attempt in range(1, RETRIES + 1):
        try:
            # the seed is ordinary blocking database code, so run it off the event loop
            await asyncio.to_thread(reseed)
            log.info("demo data reset (attempt %d)", attempt)
            return True
        except Exception:
            log.exception("demo reset attempt %d of %d failed", attempt, RETRIES)
            if attempt < RETRIES:
                await asyncio.sleep(wait)
    return False  # never let one bad run kill the loop; the next scheduled run will try again


async def nightly_loop() -> None:
    while True:
        delay = seconds_until_next_reset(datetime.now(timezone.utc))
        log.info("next demo reset in %.1f h", delay / 3600)
        await asyncio.sleep(delay)
        await reseed_with_retry()


def start() -> asyncio.Task | None:
    if not settings.demo_reset_nightly:
        return None
    return asyncio.create_task(nightly_loop(), name="demo-reset")
