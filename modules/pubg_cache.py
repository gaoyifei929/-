"""简单 TTL 缓存，避免频繁请求 PUBG API。线程安全。"""

import time
import threading


class PubgCache:
    def __init__(self, ttl_seconds: int = 300):
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.time() - ts > self._ttl:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: object):
        with self._lock:
            self._data[key] = (time.time(), value)
            self._cleanup_locked()

    def _cleanup_locked(self):
        """超过 500 条时清理过期项，防止内存泄漏。"""
        if len(self._data) < 500:
            return
        now = time.time()
        expired = [k for k, (ts, _) in self._data.items() if now - ts > self._ttl]
        for k in expired:
            del self._data[k]
