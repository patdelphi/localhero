"""程序说明：命令行备份、恢复、导出与导入本地存档，不修改案件内容。"""

import argparse
import json
import sys
from pathlib import Path

# 允许从仓库根目录之外调用本脚本。
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.archive import (  # noqa: E402
    backup_database,
    export_game,
    import_game,
    restore_database,
)

DEFAULT_DB = ROOT / "data" / "games.db"


def _build_parser() -> argparse.ArgumentParser:
    """定义备份、恢复、导出与导入四个子命令。"""
    parser = argparse.ArgumentParser(description="灰区事务所存档工具")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite 存档路径")
    sub = parser.add_subparsers(dest="command", required=True)

    backup = sub.add_parser("backup", help="生成一致性备份")
    backup.add_argument("--out", default=None, help="备份目录，默认存档同目录 backups")

    restore = sub.add_parser("restore", help="用备份覆盖当前存档")
    restore.add_argument("file", help="备份文件路径")
    restore.add_argument("--confirm", action="store_true", help="确认覆盖当前存档")

    export = sub.add_parser("export", help="导出单个存档为 JSON")
    export.add_argument("game_id", help="存档编号")
    export.add_argument("--out", required=True, help="输出 JSON 文件")

    importer = sub.add_parser("import", help="从 JSON 重建新存档")
    importer.add_argument("file", help="导出 JSON 文件")
    return parser


def _read_json(path: Path) -> dict:
    """按 UTF-8 读取 JSON，并拒绝非对象内容。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取导出文件：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("导出文件必须是 JSON 对象")
    return payload


def main(argv: list[str] | None = None) -> int:
    """执行子命令并返回进程退出码。"""
    args = _build_parser().parse_args(argv)
    db_path = Path(args.db)
    try:
        if args.command == "backup":
            target = backup_database(db_path, args.out)
            print(json.dumps({"backup": str(target)}, ensure_ascii=False))
        elif args.command == "restore":
            result = restore_database(
                db_path, Path(args.file), confirm=args.confirm,
                backup_dir=Path(args.db).parent / "backups",
            )
            print(json.dumps(result, ensure_ascii=False))
        elif args.command == "export":
            payload = export_game(db_path, args.game_id)
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps({"export": str(out), "bytes": out.stat().st_size}, ensure_ascii=False))
        else:
            payload = _read_json(Path(args.file))
            game = import_game(db_path, payload)
            print(json.dumps({"game": game}, ensure_ascii=False))
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
