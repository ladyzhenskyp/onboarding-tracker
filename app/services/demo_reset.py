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

log = logging.getLogger("demo_reset")


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


async def nightly_loop() -> None:
    while True:
        now = datetime.now(timezone.utc)
        if settings.demo_reset_schedule == "hourly":
            delay = seconds_until_next_hour(now)
        else:
            delay = seconds_until(settings.demo_reset_hour_utc, now)
        log.info("next demo reset in %.1f h", delay / 3600)
        await asyncio.sleep(delay)
        try:
            # the seed is ordinary blocking database code, so run it off the event loop
            await asyncio.to_thread(reseed)
            log.info("demo data reset")
        except Exception:  # never let one bad night kill the loop
            log.exception("demo reset failed; will try again at the next run")


def start() -> asyncio.Task | None:
    if not settings.demo_reset_nightly:
        return None
    return asyncio.create_task(nightly_loop(), name="demo-reset")
