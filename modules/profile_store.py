"""群友档案存储 — JSON 文件持久化，线程安全。"""

import json
import time
import threading
from pathlib import Path


class ProfileStore:
    def __init__(self, file_path: str):
        self._file_path = Path(file_path)
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self):
        if self._file_path.exists():
            try:
                with open(self._file_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self):
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._file_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _key(user_id: str, group_id: str | None) -> str:
        if group_id:
            return f"{group_id}:{user_id}"
        return user_id

    def set_profile(self, user_id: str, text: str, group_id: str | None = None):
        key = self._key(user_id, group_id)
        with self._lock:
            self._data[key] = {
                "profile": text,
                "updated_at": int(time.time()),
            }
            self._save()

    def get_profile(self, user_id: str, group_id: str | None = None) -> str | None:
        key = self._key(user_id, group_id)
        with self._lock:
            entry = self._data.get(key)
            return entry["profile"] if entry else None

    def list_profiles(self, group_id: str) -> dict[str, str]:
        prefix = f"{group_id}:"
        result = {}
        with self._lock:
            for key, entry in self._data.items():
                if key.startswith(prefix):
                    uid = key[len(prefix):]
                    result[uid] = entry["profile"]
        return result

    def delete_profile(self, user_id: str, group_id: str | None = None):
        key = self._key(user_id, group_id)
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._save()
