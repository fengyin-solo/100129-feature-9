"""回单管理业务规则：字段编辑、状态流转、状态口径同步与跨模块联动都收在这里。

关键约定：
- 回单以 id（主键）与「回单编号」（业务键）双重定位，签收方、签收日期等
  编辑内容只落到对应的那一张回单上，不会串到别的编号；
- 内部 status 是回单状态的唯一事实来源，台账展示用的「回单状态」字段在
  读取和写入时都与 status 对齐，保证台账、签收弹窗、配送记录看到同一结论；
- 「登记签收」联动门到门配送记录，「完成签收」由配送侧反向联动本模块。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "returntrip"
DOOR_MODULE = "door"
REQUIRED_FIELDS = ["回单编号", "关联任务", "签收方"]
# 签收弹窗里允许改动的字段；回单编号是业务键，不在编辑范围内，避免改编号导致串单
EDITABLE_FIELDS = ["签收方", "签收日期", "签收人", "异常备注"]
STATUS_ORDER = ["待签收", "已签收", "有异常", "已上传"]
ACTION_RULES = {"登记签收": "已签收", "记录异常": "有异常", "上传回单": "已上传"}
NEGATIVE_ACTIONS = {"记录异常"}

# 门到门配送侧的状态序列（放在这里避免双向 import 造成循环依赖）
DOOR_STATUS_ORDER = ["待配送", "配送中", "已送达", "已签收"]
DOOR_SIGNED = "已签收"

MAX_HISTORY = 50


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    """让展示字段「回单状态」与内部 status 保持一致，列表与详情走同一个口径。"""
    entry["回单状态"] = entry.get("status")
    return entry


def _add_history(entry: dict[str, Any], summary: str, values: dict[str, Any]) -> None:
    """追加一条修改痕迹；历史只追加不改写，便于核对“改过的是不是当初那一份”。"""
    history = entry.setdefault("history", [])
    history.append({
        "time": date.today().isoformat(),
        "summary": summary,
        "fields": {k: v for k, v in values.items()},
    })
    del history[:-MAX_HISTORY]


def _sync_to_door(entry: dict[str, Any]) -> None:
    """回单登记签收后，把关联配送任务（关联任务 == 任务编号）同步成已签收。"""
    task_no = str(entry.get("关联任务") or "").strip()
    if not task_no:
        return
    task = store.find_by_field(DOOR_MODULE, "任务编号", task_no)
    if task is None:
        return
    task["status"] = DOOR_SIGNED
    task["配送状态"] = DOOR_SIGNED
    task["pending"] = False
    task["abnormal"] = False


class ReturntripService:
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
            rows = [row for row in rows if keyword in str(row.get("回单编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def status_stats(self) -> list[dict[str, Any]]:
        """按回单状态分组统计，台账卡片、筛选分组都取这份数据，避免两个入口结论不一。"""
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
        code = str(values.get("回单编号") or "").strip()
        if store.find_by_field(MODULE, "回单编号", code) is not None:
            return None, ["回单编号"]
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["回单编号"] = code
        entry["关联任务"] = str(values.get("关联任务") or "").strip()
        for field in EDITABLE_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry["回单照片"] = str(values.get("回单照片") or "").strip()
        entry["status"] = STATUS_ORDER[0]
        entry["回单状态"] = entry["status"]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["history"] = []
        _add_history(entry, "登记回执单", {"回单编号": code})
        rows.append(entry)
        return _normalize(dict(entry)), []

    def update_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """保存签收弹窗里的编辑：只改提交的字段，且只改对应 id 的那一张回单。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"回执单 {entry_id} 不存在或已归档"
        changed: dict[str, Any] = {}
        for field in EDITABLE_FIELDS:
            if field in values:
                new_value = str(values.get(field) or "").strip()
                if str(entry.get(field) or "") != new_value:
                    changed[field] = new_value
                entry[field] = new_value
        # 照片地址也允许随表单一起保存
        if "回单照片" in values:
            new_photo = str(values.get("回单照片") or "").strip()
            if str(entry.get("回单照片") or "") != new_photo:
                changed["回单照片"] = new_photo
            entry["回单照片"] = new_photo
        if changed:
            _add_history(entry, "编辑签收信息", changed)
        return _normalize(dict(entry)), ""

    def save_photo(self, entry_id: int, photo_url: str) -> tuple[dict[str, Any] | None, str]:
        """把上传成功的照片挂到对应回单上；照片随回单一起留存，不会被后续编辑冲掉。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"回执单 {entry_id} 不存在或已归档"
        old = str(entry.get("回单照片") or "")
        entry["回单照片"] = photo_url
        if old != photo_url:
            _add_history(entry, "上传回单照片", {"回单照片": photo_url})
        return _normalize(dict(entry)), ""

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"回执单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于回单管理可执行范围"
        target = ACTION_RULES[action]

        # 签收弹窗里一起提交的签收方、签收日期先合并出来，校验通过后再写入，
        # 避免缺字段时把半截输入留在内存里
        merged = {field: str(entry.get(field) or "") for field in EDITABLE_FIELDS}
        if values:
            for field in EDITABLE_FIELDS:
                if field in values:
                    merged[field] = str(values.get(field) or "").strip()
        if action == "登记签收":
            missing = [name for name in ("签收方", "签收日期") if not merged[name]]
            if missing:
                return None, f"登记签收前需补全：{'、'.join(missing)}"
        elif action == "记录异常":
            if not merged["异常备注"]:
                return None, "记录异常前需填写异常备注"

        # 已上传是归档终态，不允许再被签收/异常动作回退
        if entry.get("status") == "已上传" and target != "已上传":
            return None, "回单已上传归档，如需修改请先联系管理员撤销归档"

        field_updates: dict[str, Any] = {}
        for field in EDITABLE_FIELDS:
            if values and field in values and str(entry.get(field) or "") != merged[field]:
                field_updates[field] = merged[field]
            entry[field] = merged[field]

        # 显式动作直接表达操作员的结论：登记签收→已签收、记录异常→有异常
        entry["status"] = target
        _normalize(entry)
        entry["pending"] = entry["status"] != STATUS_ORDER[-1]
        entry["abnormal"] = entry["status"] == "有异常"

        summary = action
        history_values = dict(field_updates)
        history_values["status"] = entry["status"]
        _add_history(entry, summary, history_values)

        if action == "登记签收":
            _sync_to_door(entry)
        return _normalize(dict(entry)), f"回执单已{action}"
