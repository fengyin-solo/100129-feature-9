"""回单管理业务规则：状态流转、字段校验、签收编辑与配送记录同步都收在这里。

关键约定：
- 签收方、签收日期、签收人、异常备注、回单照片只挂在对应的回单编号（id 与
  「回单编号」唯一）上，按 id 定位、按编号查重，不会写到别的记录上。
- 对外只有一个状态口径：内部 ``status`` 与台账列「回单状态」始终一致，
  回单台账、签收弹窗、配送记录三处看到的同一张回单状态相同。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "returntrip"
DOOR_MODULE = "door"
REQUIRED_FIELDS = ["回单编号", "关联任务", "签收方"]
# 签收弹窗里可编辑的字段；回单编号只在登记时填写，历史记录不允许改编号。
EDITABLE_FIELDS = ["关联任务", "签收方", "签收日期", "签收人", "异常备注", "回单照片"]
STATUS_ORDER = ["待签收", "已签收", "有异常", "已上传"]
ACTION_RULES = {"登记签收": "已签收", "记录异常": "有异常", "上传回单": "已上传"}
NEGATIVE_ACTIONS = ["记录异常"]


def _refresh_flags(entry: dict[str, Any]) -> None:
    """让内部标记与唯一状态口径保持一致，概览、分组统计都以 status 为准。"""
    status = str(entry.get("status") or STATUS_ORDER[0])
    entry["回单状态"] = status
    entry["pending"] = status != "已上传"
    entry["abnormal"] = status == "有异常" or bool(str(entry.get("异常备注") or "").strip())


def sync_receipt_status(receipt: dict[str, Any], status: str) -> dict[str, Any]:
    """回单状态发生变化时，同步台账展示列与关联配送任务里的回单状态。"""
    receipt["status"] = status
    _refresh_flags(receipt)
    task_no = str(receipt.get("关联任务") or "").strip()
    if task_no:
        task = store.find_by(DOOR_MODULE, "任务编号", task_no)
        if task is not None:
            task["回单状态"] = status
    return receipt


def _task_receipt(task_no: str) -> dict[str, Any] | None:
    """按配送任务编号找到它挂的回单（回单的「关联任务」= 配送任务编号）。"""
    if not task_no:
        return None
    for row in store.rows(MODULE):
        if str(row.get("关联任务") or "").strip() == task_no:
            return row
    return None


def snapshot_for_task(task: dict[str, Any]) -> None:
    """把配送记录里那张回单的状态镜像到任务上，供配送列表展示。"""
    receipt = _task_receipt(str(task.get("任务编号") or "").strip())
    if receipt is not None:
        task["回单状态"] = receipt.get("status")


class ReturntripService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        for row in rows:
            _refresh_flags(row)
            task = store.find_by(DOOR_MODULE, "任务编号", row.get("关联任务"))
            if task is not None:
                task["回单状态"] = row["status"]
        matched = rows
        if keyword:
            matched = [row for row in matched if keyword in str(row.get("回单编号", ""))]
        if status:
            matched = [row for row in matched if row.get("status") == status]
        total = len(matched)
        start = max(page - 1, 0) * size
        return matched[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is not None:
            _refresh_flags(entry)
        return entry

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        receipt_no = str(values.get("回单编号") or "").strip()
        if store.find_by(MODULE, "回单编号", receipt_no) is not None:
            raise ValueError(f"回单编号 {receipt_no} 已存在，重复登记会覆盖历史回单，请换一个编号")
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["回单编号"] = receipt_no
        for field in ["关联任务", "签收方", "签收日期", "签收人", "异常备注", "回单照片"]:
            entry[field] = str(values.get(field) or "").strip()
        entry["status"] = STATUS_ORDER[0]
        _refresh_flags(entry)
        rows.append(entry)
        # 新回单若已经关联配送任务，把初始状态同步过去，保证两个入口结论一致。
        snapshot_for_task(store.find_by(DOOR_MODULE, "任务编号", entry["关联任务"]) or {})
        return entry, []

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """签收弹窗保存：只改这一张回单，未提交的字段保持原值，绝不串到其他编号上。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"回执单 {entry_id} 不存在或已归档"

        new_no = values.get("回单编号")
        if new_no is not None and str(new_no).strip() and str(new_no).strip() != str(entry.get("回单编号")):
            if store.find_by(MODULE, "回单编号", new_no) is not None:
                return None, f"回单编号 {str(new_no).strip()} 已被其他回单占用"
            entry["回单编号"] = str(new_no).strip()

        for field in EDITABLE_FIELDS:
            if field in values:
                entry[field] = str(values.get(field) or "").strip()

        # 状态以弹窗里显式选择的为准；没选时按内容推导，保证台账与弹窗结论一致。
        target = str(values.get("status") or "").strip()
        if target not in STATUS_ORDER:
            if entry.get("异常备注"):
                target = "有异常"
            elif entry.get("回单照片"):
                target = "已上传"
            elif entry.get("签收方") and entry.get("签收日期"):
                target = "已签收"
            else:
                target = str(entry.get("status") or STATUS_ORDER[0])
        sync_receipt_status(entry, target)
        return entry, "回单签收信息已保存"

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"回执单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于回单管理可执行范围"

        # 动作弹窗里一并填写的签收方/签收日期/异常备注/照片同样要落到这张回单上。
        values = values or {}
        if action == "登记签收":
            for field in ["签收方", "签收日期", "签收人"]:
                if values.get(field):
                    entry[field] = str(values[field]).strip()
            if not entry.get("签收方") or not entry.get("签收日期"):
                return None, "登记签收需要同时填写签收方与签收日期"
        elif action == "记录异常":
            remark = str(values.get("异常备注") or entry.get("异常备注") or "").strip()
            if not remark:
                return None, "记录异常需要填写异常备注"
            entry["异常备注"] = remark
        elif action == "上传回单":
            photo = str(values.get("回单照片") or entry.get("回单照片") or "").strip()
            if not photo:
                return None, "上传回单需要先选择回单照片"
            entry["回单照片"] = photo

        sync_receipt_status(entry, ACTION_RULES[action])
        return entry, f"回执单已{action}"


def mark_signed_by_task(task_no: str) -> None:
    """配送记录执行「完成签收」时，把挂在该任务上的回单同步成已签收。"""
    receipt = _task_receipt(task_no)
    if receipt is None:
        return
    if not receipt.get("签收日期"):
        receipt["签收日期"] = date.today().isoformat()
    sync_receipt_status(receipt, "已签收")
