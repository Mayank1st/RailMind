import asyncio
from collections.abc import Awaitable

# One event loop per worker PROCESS, shared across every Celery task module.
# All async DB work MUST run on the same loop: asyncpg pooled connections bind
# to the loop that first used them, so running a later task on a different loop
# raises "Future attached to a different loop". A single process-wide loop (not
# one loop per task module) is what prevents that.
_worker_loop: asyncio.AbstractEventLoop | None = None


def run_in_worker_loop(coro: Awaitable) -> None:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    _worker_loop.run_until_complete(coro)
