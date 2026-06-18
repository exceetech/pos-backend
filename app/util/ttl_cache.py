"""Minimal bounded, thread-safe TTL cache (no external dependency).

Evicts expired entries on access and caps the number of keys so module-level
caches can't grow without bound across many shops.
"""

import time
import threading


class TTLCache:
    def __init__(self, ttl_seconds: int, max_size: int = 512):
        self._ttl = ttl_seconds
        self._max = max_size
        self._store = {}          # key -> (expires_at_epoch, value)
        self._lock = threading.Lock()

    def get(self, key):
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry[0] <= now:          # expired → drop it
                self._store.pop(key, None)
                return None
            return entry[1]

    def set(self, key, value):
        now = time.time()
        with self._lock:
            if len(self._store) >= self._max and key not in self._store:
                # Sweep expired entries first; if still full, drop the soonest-expiring.
                for k in [k for k, v in self._store.items() if v[0] <= now]:
                    self._store.pop(k, None)
                while len(self._store) >= self._max:
                    oldest = min(self._store, key=lambda k: self._store[k][0])
                    self._store.pop(oldest, None)
            self._store[key] = (now + self._ttl, value)

    def pop(self, key):
        with self._lock:
            self._store.pop(key, None)
