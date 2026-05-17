import os
import re
from pathlib import Path
import yaml

_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _resolve_env(value: str) -> str:
    """替换 ${VAR_NAME} 为环境变量值。"""

    def replacer(match):
        env_name = match.group(1)
        env_value = os.environ.get(env_name)
        if env_value is None:
            raise ValueError(
                f"环境变量 {env_name} 未设置，配置文件需要它"
            )
        return env_value

    return _ENV_VAR_RE.sub(replacer, value)


def _walk_and_resolve(obj):
    """递归遍历配置对象，替换所有字符串中的环境变量。"""
    if isinstance(obj, dict):
        return {k: _walk_and_resolve(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_and_resolve(v) for v in obj]
    if isinstance(obj, str):
        return _resolve_env(obj)
    return obj


def _load_dotenv(dotenv_path: Path):
    """加载 .env 文件到 os.environ（不覆盖已有环境变量）。"""
    if not dotenv_path.exists():
        return
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key not in os.environ:
                os.environ[key] = value


def load_config(path: str) -> dict:
    """加载 YAML 配置文件，自动解析环境变量占位符。"""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    # 自动加载同目录下的 .env 文件
    _load_dotenv(config_path.parent / ".env")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return _walk_and_resolve(raw)
