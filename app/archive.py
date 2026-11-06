"""程序说明：提供 SQLite 在线备份、恢复以及可移植的存档导出导入。"""

import json
import shutil
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.branching import _purge
from app.replay_engine import ReplayEngine, ReplayUnavailable
from app.store import Database

EXPORT_FORMAT = "grey-zone-save"
EXPORT_VERSION = 1
_VOLATILE_KEYS = {"created_at", "updated_at", "completed_at", "_rowid"}
_BRANCH_KEYS = {
    "parent_game_id",
    "fork_action_id",
    "fork_action_index",
    "branch_label",
    "branch_status",
    "branch_created_at",
}


def _utc_stamp() -> str:
    """生成备份文件名使用的 UTC 时间戳；微秒避免同一秒内相互覆盖。"""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def _check_integrity(path: Path) -> None:
    """用 SQLite quick_check 确认备份可读取且结构完整。"""
    try:
        with closing(sqlite3.connect(path)) as conn:
            result = conn.execute("PRAGMA quick_check").fetchone()[0]
    except sqlite3.Error as exc:
        raise ValueError(f"数据库文件无法读取：{exc}") from exc
    if result != "ok":
        raise ValueError(f"数据库完整性检查失败：{result}")


def backup_database(db_path: str | Path, backup_dir: str | Path | None = None) -> Path:
    """使用在线备份接口生成一致性副本，不复制半成品 WAL 文件。"""
    source = Path(db_path)
    if not source.exists():
        raise FileNotFoundError(f"存档数据库不存在：{source}")
    target_dir = Path(backup_dir) if backup_dir else source.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}-{_utc_stamp()}.db"
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    _check_integrity(target)
    return target


def restore_database(
    db_path: str | Path,
    backup_path: str | Path,
    confirm: bool = False,
    backup_dir: str | Path | None = None,
) -> dict:
    """用备份覆盖当前库；必须确认，并先保留当前库的安全副本。"""
    if not confirm:
        raise ValueError("恢复存档需要确认")
    backup = Path(backup_path)
    if not backup.exists():
        raise FileNotFoundError(f"备份文件不存在：{backup}")
    _check_integrity(backup)
    target = Path(db_path)
    safety = backup_database(target, backup_dir) if target.exists() else None
    try:
        # 先移除主库与 WAL/SHM 边车，避免旧页在替换后被 SQLite 重放。
        for suffix in ("", "-wal", "-shm"):
            sidecar = Path(str(target) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        shutil.copy2(backup, target)
    except OSError as exc:
        raise ValueError(f"恢复失败：{exc}") from exc
    _check_integrity(target)
    return {
        "restored_from": str(backup),
        "safety_copy": str(safety) if safety else None,
    }


def _scrub(value):
    """移除时间戳与分支链接等不可移植字段，保留机械状态。"""
    if isinstance(value, dict):
        return {
            key: _scrub(item)
            for key, item in value.items()
            if key not in _VOLATILE_KEYS and key not in _BRANCH_KEYS
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def export_game(db_path: str | Path, game_id: str) -> dict:
    """导出一个存档的完整机械历史与玩家假设。"""
    database = Database(db_path)
    engine = ReplayEngine(database)
    records = engine.export_records(game_id)
    hypotheses = database.get_hypotheses(game_id)
    return {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_game_id": game_id,
        "case_id": records["game"].get("case_id") or "C01",
        "records": _scrub(records),
        "hypotheses": [item["text"] for item in hypotheses],
    }


def import_game(db_path: str | Path, payload: dict) -> dict:
    """校验导出内容后重放为全新存档；失败时清理半成品。"""
    if not isinstance(payload, dict):
        raise ValueError("导入内容必须是 JSON 对象")
    if payload.get("format") != EXPORT_FORMAT:
        raise ValueError("导出格式不受支持")
    if payload.get("format_version") != EXPORT_VERSION:
        raise ValueError("导出格式版本不受支持")
    records = payload.get("records")
    if not isinstance(records, dict):
        raise ValueError("导出内容缺少存档记录")
    hypotheses = payload.get("hypotheses") or []
    if not isinstance(hypotheses, list) or any(not isinstance(text, str) for text in hypotheses):
        raise ValueError("玩家假设必须是文本列表")

    database = Database(db_path).initialize()
    engine = ReplayEngine(database)
    game_id = uuid.uuid4().hex
    try:
        rebuilt = engine.import_records(database, game_id, records)
        with database.transaction() as conn:
            # 叙事文本由模型产出，重放不生成，需从导出记录回填。
            for event in rebuilt["events"]:
                new_action_id = rebuilt["action_map"].get(event["action_id"])
                if not new_action_id:
                    continue
                conn.execute(
                    "INSERT INTO events(game_id, action_id, kind, payload_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        game_id, new_action_id, event["kind"],
                        json.dumps(event["payload"], ensure_ascii=False),
                    ),
                )
            for text in hypotheses:
                cleaned = text.strip()
                if cleaned:
                    conn.execute(
                        "INSERT INTO player_hypotheses(id, game_id, text) VALUES (?, ?, ?)",
                        (uuid.uuid4().hex, game_id, cleaned),
                    )
    except (ReplayUnavailable, KeyError, ValueError, sqlite3.Error) as exc:
        _purge(database, game_id)
        raise ValueError(f"导出存档无法重建：{exc}") from exc
    except Exception:
        _purge(database, game_id)
        raise
    return database.get_game(game_id)
