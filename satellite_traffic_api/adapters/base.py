from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, TypeVar, Generic
from satellite_traffic_api.cache.backend import CacheBackend
from satellite_traffic_api.config import Settings

T = TypeVar("T")


class BaseAdapter(ABC, Generic[T]):
    def __init__(self, settings: Settings, cache: CacheBackend) -> None:
        self.settings = settings
        self.cache = cache

    @abstractmethod
    async def fetch_raw(self, **kwargs) -> Any:
        """Hit external source and return raw parsed data."""

    @abstractmethod
    def normalize(self, raw: Any, **kwargs) -> T:
        """Convert raw response into typed model(s)."""

    @abstractmethod
    def cache_key(self, **kwargs) -> str:
        """Deterministic cache key string for this query."""

    @property
    @abstractmethod
    def ttl_seconds(self) -> int:
        """How long to cache this data type."""

    async def get(self, **kwargs) -> T:
        """Cache-aside: check cache → fetch on miss → store result."""
        key = self.cache_key(**kwargs)
        cached = await self.cache.get(key)
        if cached is not None:
            return self.normalize(cached, **kwargs)
        raw = await self.fetch_raw(**kwargs)
        await self.cache.set(key, raw, ttl=self.ttl_seconds)
        return self.normalize(raw, **kwargs)
