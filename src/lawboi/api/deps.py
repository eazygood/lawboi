import asyncio
from typing import Optional

from lawboi.config.settings import load_settings
from lawboi.config.composition import build_container, Container

_container: Optional[Container] = None
_lock = asyncio.Lock()


async def get_container() -> Container:
    global _container
    if _container is None:
        async with _lock:
            if _container is None:
                _container = await build_container(load_settings())
    return _container


async def get_retrieval():
    return (await get_container()).retrieval


async def get_answer():
    return (await get_container()).answer


async def get_store():
    return (await get_container()).store


async def get_moderation():
    return (await get_container()).moderation


async def get_embedder():
    return (await get_container()).embedder


async def get_cache():
    return (await get_container()).cache


async def get_settings():
    return (await get_container()).settings
