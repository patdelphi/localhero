"""程序说明：把游戏日志写成逐行 JSON，便于本地排障且默认不记录任何密钥。"""

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "localhero"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


class JsonFormatter(logging.Formatter):
    """输出固定字段的结构化日志行。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    log_dir: str | Path | None = None,
    level: str | None = None,
) -> dict:
    """配置 localhero 日志：控制台与滚动文件同时输出 JSON。"""
    target_dir = Path(
        log_dir or os.getenv("GREY_ZONE_LOG_DIR") or "data/logs"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / "app.jsonl"
    logger = logging.getLogger(_LOGGER_NAME)

    # 重复创建应用时先移除旧处理器，避免同一行写多次。
    for handler in list(logger.handlers):
        if getattr(handler, "_grey_zone", False):
            logger.removeHandler(handler)
            handler.close()

    chosen_level = (level or os.getenv("GREY_ZONE_LOG_LEVEL") or "INFO").upper()
    logger.setLevel(chosen_level)
    logger.propagate = False

    formatter = JsonFormatter()
    file_handler = RotatingFileHandler(
        file_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler._grey_zone = True

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler._grey_zone = True

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return {"log_file": str(file_path), "level": chosen_level}
