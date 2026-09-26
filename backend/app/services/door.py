"""门到门配送业务规则：字段流转与回单状态联动都收在这里。

「完成签收」会按任务编号找到关联回单，把回单台账同步成已签收；
反过来回单侧「登记签收」也会把配送记录推进到已签收。两边状态口径一致，
不会再出现同一笔配送在两个模块看到不同结论。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "door"
RETURNTRIP_MODULE = "returntrip"
REQUIRED_FIELDS = ["任务编号", "关联调度", "配送站点"]
STATUS_ORDER = ["待配送", "配送中", "已送达", "已签收"]
ACTION_RULES = {"开始配送": "配送中", "确认送达": "已送达", "完成签收": "已签收"}
NEGATIVE_ACTIONS = []

# 回单侧状态序列（放在这里避免双向 import 造成循环依赖）
RETURNTRIP_STATUS_ORDER = ["待签收", "已签收", "有异常", "已上传"]
RETURNTRIP_SIGNED = "已签收"


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    """展示字段「配送状态」始终跟随内部 status。"""
    entry["配送状态"] = entry.get("status")
    return entry


def _sync_to_returntrip(entry: dict[str, Any]) -> None:
    """配送完成签收后，把关联回单（回单.关联任务 == 任务编号）同步成已签收。"""
    task_no = str(entry.get("任务编号") or "").strip()
    if not task_no:
        return
    receipt = store.find_by_field(RETURNTRIP_MODULE, "关联任务", task_no)
    if receipt is None:
        return
    # 已上传的回单是终态、有异常的回单保留异常结论，都不被配送侧动作覆盖
    if receipt.get("status") in {"已上传", "有异常"}:
        return
    receipt["status"] = RETURNTRIP_SIGNED
    receipt["回单状态"] = RETURNTRIP_SIGNED
    receipt["abnormal"] = False


class DoorService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [_normalize(dict(row)) for row in store.rows(MODULE)]
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("任务编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def status_stats(self) -> list[dict[str, Any]]:
        counts = {name: 0 for name in STATUS_ORDER}
        for row in store.rows(MODULE):
            status = row.get("status")
            if status in counts:
                counts[status] += 1
        return [{"label": name, "value": counts[name]} for name in STATUS_ORDER]

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _normalize(dict(entry)) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        _normalize(entry)
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"配送任务 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于门到门配送可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        _normalize(entry)
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "完成签收":
            _sync_to_returntrip(entry)
        return entry, f"配送任务已{action}"
