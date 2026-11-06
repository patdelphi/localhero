"""程序说明：从任意已记录行动创建分支存档，维护软删除归档与分支树。

分支通过确定性重放源存档的历史前缀得到，原存档全程只读；
归档只改状态、不删除数据，可随时恢复。
"""

import json
import uuid
from datetime import datetime, timezone

from app.replay_engine import ReplayEngine

# 单个存档允许的直属分支上限，避免本地库无限增长。
MAX_BRANCHES = 10
# 分支树单次返回的节点上限，超出后不再展开。
MAX_TREE_NODES = 40
# 分支创建失败时需要按外键顺序清理的表。
_BRANCH_TABLES = (
    "case_facts",
    "clock_changes",
    "knowledge_records",
    "social_states",
    "character_history",
    "local_plans",
    "player_hypotheses",
    "events",
    "actions",
    "replay_baselines",
    "case_states",
)


def _now() -> str:
    """使用 UTC 秒级时间，保证跨设备排序稳定。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _purge(database, game_id: str) -> None:
    """在单一事务内清理半成品分支，避免留下孤立行。"""
    with database.transaction() as conn:
        for table in _BRANCH_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE game_id=?", (game_id,))
        conn.execute("DELETE FROM games WHERE id=?", (game_id,))


def create_branch(database, game_id: str, fork_action_id: str, label: str | None) -> dict:
    """在指定行动之后创建分支，返回新存档行；源存档不写入任何数据。"""
    source = database.get_game(game_id)
    if source.get("branch_status") == "archived":
        raise ValueError("归档分支不能继续分叉")
    text = (label or "").strip()
    if len(text) > 40:
        raise ValueError("分支名称不能超过 40 个字符")
    with database.connect() as conn:
        children = conn.execute(
            "SELECT COUNT(*) FROM games WHERE parent_game_id=?", (game_id,)
        ).fetchone()[0]
    if children >= MAX_BRANCHES:
        raise ValueError(f"每个存档最多创建 {MAX_BRANCHES} 条分支")

    branch_id = uuid.uuid4().hex
    engine = ReplayEngine(database)
    try:
        rebuilt = engine.rebuild_prefix(
            database, branch_id, game_id, fork_action_id
        )
        with database.transaction() as conn:
            conn.execute(
                """
                UPDATE games
                SET parent_game_id=?, fork_action_id=?, fork_action_index=?,
                    branch_label=?, branch_status='active', branch_created_at=?
                WHERE id=?
                """,
                (
                    game_id,
                    fork_action_id,
                    len(rebuilt["action_map"]),
                    text or f"分支 {children + 1}",
                    _now(),
                    branch_id,
                ),
            )
            # 只复制展示类事件；机械状态与事实已由重放确定性重建。
            for event in rebuilt["events"]:
                new_action_id = rebuilt["action_map"].get(event["action_id"])
                if not new_action_id:
                    continue
                conn.execute(
                    "INSERT INTO events(game_id, action_id, kind, payload_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        branch_id,
                        new_action_id,
                        event["kind"],
                        json.dumps(event["payload"], ensure_ascii=False),
                    ),
                )
    except Exception:
        # 任何一步失败都回滚分支已有写入，再抛出原始错误。
        _purge(database, branch_id)
        raise
    return database.get_game(branch_id)


def set_branch_status(
    database, game_id: str, status: str, confirm: bool
) -> dict:
    """归档或恢复分支；必须显式确认，根存档不允许归档。"""
    if status not in {"archived", "active"}:
        raise ValueError("未知的分支状态")
    if not confirm:
        raise ValueError("归档或恢复分支需要确认")
    game = database.get_game(game_id)
    if not game.get("parent_game_id"):
        raise ValueError("根存档不能归档")
    if (game.get("branch_status") or "active") == status:
        return game
    with database.transaction() as conn:
        conn.execute("UPDATE games SET branch_status=? WHERE id=?", (status, game_id))
    return database.get_game(game_id)


def branch_tree(database, game_id: str) -> dict:
    """返回以根存档为起点的分支树与各节点关键状态摘要。"""
    database.get_game(game_id)  # 校验当前存档存在
    root_id = game_id
    seen = {root_id}
    while True:
        current = database.get_game(root_id)
        parent = current.get("parent_game_id")
        if not parent or parent in seen:
            break
        seen.add(root_id)
        root_id = parent

    items = []
    queue = [root_id]
    visited = set()
    while queue and len(items) < MAX_TREE_NODES:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)
        current = database.get_game(current_id)
        state = database.get_case_state(current_id)
        items.append(
            {
                "game_id": current_id,
                "parent_game_id": current.get("parent_game_id"),
                "fork_action_id": current.get("fork_action_id"),
                "fork_action_index": current.get("fork_action_index"),
                "branch_label": current.get("branch_label"),
                "branch_status": current.get("branch_status") or "active",
                "is_root": current.get("parent_game_id") is None,
                "is_current": current_id == game_id,
                "state": {
                    "phase": state["phase"],
                    "location": state["location"],
                    "clock": state["clock"],
                    "ending": state["ending"],
                    "revision": state["revision"],
                    "clues": len(state["clues"]),
                    "actions": database.count_actions(current_id),
                },
            }
        )
        with database.connect() as conn:
            children = conn.execute(
                "SELECT id FROM games WHERE parent_game_id=? ORDER BY created_at, id",
                (current_id,),
            ).fetchall()
        queue.extend(row["id"] for row in children)
    return {
        "root_game_id": root_id,
        "current_game_id": game_id,
        "items": items,
    }
