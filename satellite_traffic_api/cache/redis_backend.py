from __future__ import annotations
from typing import Any
import orjson
import redis.asyncio as aioredis
from .backend import CacheBackend

_PREFIX = "satapi:"


class RedisCacheBackend(CacheBackend):
    def __init__(self, redis_url: str) -> None:
        self._client = aioredis.from_url(redis_url, decode_responses=False)

    async def get(self, key: str) -> Any | None:
        raw = await self._client.get(_PREFIX + key)
        if raw is None:
            return None
        return orjson.loads(raw)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        await self._client.setex(_PREFIX + key, ttl, orjson.dumps(value))

    async def delete(self, key: str) -> None:
        await self._client.delete(_PREFIX + key)

    async def exists(self, key: str) -> bool:
        return bool(await self._client.exists(_PREFIX + key))

    async def close(self) -> None:
        await self._client.aclose()
