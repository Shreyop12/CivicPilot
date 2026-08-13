import hashlib
import json
import time
from typing import Any, Callable


class QueryCache:
    """In-process TTL cache keyed by normalized query parameters."""

    def __init__(
        self,
        maxsize: int = 512,
        ttl_seconds: int = 300,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._store: dict[str, tuple[float, Any]] = {}
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._clock = clock

    @staticmethod
    def make_key(*args: Any, **kwargs: Any) -> str:
        raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self._maxsize and key not in self._store:
            oldest_key = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest_key]
        self._store[key] = (self._clock() + self._ttl, value)
