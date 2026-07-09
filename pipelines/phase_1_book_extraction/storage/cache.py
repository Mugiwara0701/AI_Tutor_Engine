"""
storage/cache.py — small in-process, TTL-based cache used to avoid
re-hitting Graph for metadata lookups (get_item / exists / list_directory)
that repeat during a single run (e.g. ensure_folder() being called for the
same Book path once per uploaded chapter file).

Deliberately NOT a cache of file *contents* -- only of small JSON metadata
responses -- and deliberately in-process only (no disk persistence), since
staleness across process restarts would silently hide real OneDrive
changes made from elsewhere (web UI, another machine, etc.).
"""
import time
import threading
from typing import Any, Callable, Dict, Optional, Tuple


class TTLCache:
    def __init__(self, ttl_seconds: float = 30.0):
        self._ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        """Drops every cached entry whose key starts with `prefix` --
        used after delete/move/copy/create so a stale get_item() or
        list_directory() result for an ancestor/sibling path can't leak
        through."""
        with self._lock:
            for key in [k for k in self._store if k.startswith(prefix)]:
                del self._store[key]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def get_or_set(self, key: str, compute: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = compute()
        self.set(key, value)
        return value
