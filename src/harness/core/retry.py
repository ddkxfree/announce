from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    retries: int,
    is_retryable: Callable[[BaseException], bool],
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    on_attempt: Callable[[int], None] | None = None,
) -> T:
    """Call ``fn`` with exponential backoff and jitter on retryable errors."""
    attempt = 0
    while True:
        attempt += 1
        if on_attempt:
            on_attempt(attempt)
        try:
            return await fn()
        except Exception as exc:
            if attempt > retries or not is_retryable(exc):
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            await asyncio.sleep(delay * (0.5 + random.random() / 2))
