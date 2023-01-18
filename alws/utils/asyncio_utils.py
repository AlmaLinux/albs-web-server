import asyncio


async def gather_with_concurrency(
    *coroutines,
    limit: int = 3,
):
    semaphore = asyncio.Semaphore(limit)

    async def sem_coro(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*(sem_coro(c) for c in coroutines))
