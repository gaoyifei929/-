import logging
import sys
from pathlib import Path


def setup_logging(config: dict):
    """初始化日志：同时输出到控制台和文件。"""
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper())
    file_path = log_config.get("file", "logs/app.log")
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # 控制台（强制 UTF-8，避免 Git Bash 乱码）
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # 文件
    log_file = Path(file_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
