import time
import threading
from collections import deque
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class Session:
    history: deque = field(default_factory=lambda: deque(maxlen=20))
    last_active: float = field(default_factory=time.time)

    def to_api_messages(self) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in self.history]


class SessionManager:
    """按用户/群维度管理多轮对话上下文。"""

    def __init__(self, max_rounds: int = 10, timeout_minutes: int = 30):
        self.max_rounds = max_rounds
        self.timeout_seconds = timeout_minutes * 60
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def _session_key(self, user_id: str, group_id: str | None) -> str:
        # 群聊时按用户隔离上下文，私聊时只按用户
        if group_id:
            return f"{group_id}:{user_id}"
        return user_id

    def get_history(self, user_id: str, group_id: str | None = None) -> list[dict]:
        key = self._session_key(user_id, group_id)
        with self._lock:
            self._expire_if_needed(key)
            sess = self._sessions.get(key)
            if sess is None:
                return []
            sess.last_active = time.time()
            return sess.to_api_messages()

    def add_message(
        self, user_id: str, role: str, content: str, group_id: str | None = None
    ):
        key = self._session_key(user_id, group_id)
        with self._lock:
            sess = self._sessions.get(key)
            if sess is None:
                sess = Session()
                sess.history = deque(maxlen=self.max_rounds * 2)
                self._sessions[key] = sess
            sess.history.append(ChatMessage(role=role, content=content))
            sess.last_active = time.time()

    def clear(self, user_id: str, group_id: str | None = None):
        key = self._session_key(user_id, group_id)
        with self._lock:
            self._sessions.pop(key, None)

    def get_status(self, user_id: str, group_id: str | None = None) -> dict:
        key = self._session_key(user_id, group_id)
        with self._lock:
            sess = self._sessions.get(key)
            if sess is None:
                return {"messages": 0, "rounds": 0}
            msg_count = len(sess.history)
            return {
                "messages": msg_count,
                "rounds": msg_count // 2,
                "idle_seconds": int(time.time() - sess.last_active),
            }

    def _expire_if_needed(self, key: str):
        sess = self._sessions.get(key)
        if sess is None:
            return
        if time.time() - sess.last_active > self.timeout_seconds:
            del self._sessions[key]

    def cleanup_expired(self):
        """清理所有过期会话，可被定时任务调用。"""
        with self._lock:
            expired = [
                k
                for k, s in self._sessions.items()
                if time.time() - s.last_active > self.timeout_seconds
            ]
            for k in expired:
                del self._sessions[k]
