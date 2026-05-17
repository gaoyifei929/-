import time
import threading
from collections import defaultdict


class RateLimiter:
    """基于滑动窗口的每用户限流 + 全局 QPS 控制。"""

    def __init__(self, window_seconds: int = 60, max_messages: int = 10, global_qps: int = 5):
        self.window = window_seconds
        self.max_messages = max_messages
        self.min_interval = 1.0 / global_qps if global_qps > 0 else 0

        self._user_requests: dict[str, list[float]] = defaultdict(list)
        self._last_global: float = 0.0
        self._lock = threading.Lock()

    def is_allowed(self, user_id: str) -> bool:
        now = time.time()
        with self._lock:
            # 全局 QPS
            if self.min_interval > 0:
                elapsed = now - self._last_global
                if elapsed < self.min_interval:
                    return False
                self._last_global = now

            # 每用户窗口限流
            timestamps = self._user_requests[user_id]
            # 清理过期记录
            cutoff = now - self.window
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)

            if len(timestamps) >= self.max_messages:
                return False

            timestamps.append(now)

        # 定期清理空用户记录
        if len(self._user_requests) > 10000:
            with self._lock:
                empty = [k for k, v in self._user_requests.items() if not v]
                for k in empty:
                    del self._user_requests[k]

        return True

    def get_status(self, user_id: str) -> dict:
        with self._lock:
            timestamps = self._user_requests.get(user_id, [])
            cutoff = time.time() - self.window
            recent = [t for t in timestamps if t >= cutoff]
            return {
                "recent_count": len(recent),
                "limit": self.max_messages,
                "window_seconds": self.window,
            }
