"""Concurrency utilities for tokenviz."""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")
R = TypeVar("R")

DEFAULT_CONCURRENCY = int(os.environ.get("BRAGGRID_CONCURRENCY", "4"))


async def pool_map(
    items: list[T],
    fn: Callable[[T], Awaitable[R]],
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[R]:
    """Run async function over items with bounded concurrency."""
    semaphore = asyncio.Semaphore(concurrency)
    results: list[R] = []

    async def bounded(item: T) -> R:
        async with semaphore:
            return await fn(item)

    tasks = [asyncio.create_task(bounded(item)) for item in items]
    results = await asyncio.gather(*tasks)
    return list(results)


def pool_map_sync(
    items: list[T],
    fn: Callable[[T], R],
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[R]:
    """Run sync function over items using ThreadPoolExecutor."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        return list(executor.map(fn, items))
