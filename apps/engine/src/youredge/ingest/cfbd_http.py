"""Shared CFBD request helper: retry what is transient, surface what is not.

Written after a backfill quietly stopped at 81 games of 900 and still exited 0.
Two faults, both worth not repeating:

  * `tenacity` wraps the final failure in `RetryError`, so callers catching
    `httpx.HTTPStatusError` never saw it. The loop's own error handling was dead
    code and the job reported success on a fraction of the data.
  * The retry applied to every status alike, so a 401 was retried three times and
    a 429 got the same treatment as a bad parameter.

Rate limiting is the normal failure here — two ingests against one API key will
hit it — so 429 backs off and retries, 5xx retries, and everything else raises
immediately with the status attached.
"""

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}


class CFBDError(RuntimeError):
    """A CFBD request that failed in a way retrying will not fix."""

    def __init__(self, status: int, url: str, body: str = ""):
        self.status = status
        super().__init__(f"CFBD {status} for {url}: {body[:200]}")


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    *,
    attempts: int = 4,
    base_delay: float = 2.0,
):
    """GET returning parsed JSON, retrying only transient failures.

    Raises CFBDError on a non-transient status, or after the last attempt at a
    transient one — never silently returns partial or empty data.
    """
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            r = await client.get(url, params=params)
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last = e
            if attempt == attempts:
                raise CFBDError(0, url, str(e)) from e
        else:
            if r.status_code == 200:
                return r.json()
            if r.status_code not in RETRY_STATUSES:
                raise CFBDError(r.status_code, url, r.text)
            last = CFBDError(r.status_code, url, r.text)
            if attempt == attempts:
                raise last

        # Exponential backoff. A 429 means the key is being asked for too much at
        # once, which is what happens when two ingests run against it together.
        delay = base_delay * (2 ** (attempt - 1))
        log.warning("CFBD retry %d/%d in %.0fs (%s)", attempt, attempts, delay, last)
        await asyncio.sleep(delay)
