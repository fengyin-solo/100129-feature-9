"""回单管理接口：维护回执单，覆盖登记签收、记录异常、上传回单与字段编辑保存。"""
from __future__ import annotations

import base64
import binascii
import re
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.returntrip import ReturntripService
from app.store import UPLOAD_DIR

router = APIRouter(prefix="/api/returntrip", tags=["回单管理"])

service = ReturntripService()

LIST_FIELDS = ["回单编号", "关联任务", "签收方", "签收日期", "签收人", "异常备注", "回单照片", "回单状态"]
STATUSES = ["待签收", "已签收", "有异常", "已上传"]

ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
MAX_PHOTO_BYTES = 8 * 1024 * 1024
DATA_URL_RE = re.compile(r"^data:image/(?P<ext>[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$", re.S)


class PhotoPayload(BaseModel):
    """照片上传：前端把图片读成 data URL 提交，后端落盘后回传可访问地址。"""

    filename: str | None = None
    content: str


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按回单编号检索"),
    status: str | None = Query(default=None, description="待签收、已签收、有异常、已上传"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按回单编号与状态过滤回单管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def status_stats() -> dict[str, Any]:
    """按回单状态分组统计：台账卡片与状态筛选共用同一份口径。"""
    return {"module": "returntrip", "items": service.status_stats()}


# 注意：/export、/stats 必须排在 /{entry_id} 之前，否则会被当成回单 id 解析
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出回单管理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "returntrip", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条回执单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"回执单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条回执单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        if missing == ["回单编号"]:
            return ActionResult(ok=False, message="回单编号已存在，不能重复登记")
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="回执单已登记", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """保存签收弹窗里的编辑：签收方、签收日期等只更新到对应回单，不改其他记录。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="签收信息已保存", entry=entry)


@router.post("/{entry_id}/photo", response_model=ActionResult)
def upload_photo(entry_id: int, payload: PhotoPayload) -> ActionResult:
    """上传回单照片：图片随回单一起留存，重复打开仍是同一张。"""
    if service.get_entry(entry_id) is None:
        return ActionResult(ok=False, message=f"回执单 {entry_id} 不存在或已归档")
    match = DATA_URL_RE.match(payload.content.strip())
    if not match:
        return ActionResult(ok=False, message="照片内容不是有效的图片 data URL")
    ext = f".{match.group('ext').lower()}"
    if ext not in ALLOWED_PHOTO_EXT:
        return ActionResult(ok=False, message=f"不支持的图片格式：{ext}")
    try:
        raw = base64.b64decode(match.group("data"), validate=True)
    except (binascii.Error, ValueError):
        return ActionResult(ok=False, message="照片内容解码失败")
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        return ActionResult(ok=False, message="照片为空或超过 8MB 限制")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^0-9A-Za-z_-]", "", (payload.filename or "").rsplit(".", 1)[0])[:40]
    stored_name = f"returntrip-{entry_id}-{safe_stem or 'photo'}-{uuid.uuid4().hex[:8]}{ext}"
    (UPLOAD_DIR / stored_name).write_bytes(raw)
    photo_url = f"/uploads/{stored_name}"

    entry, message = service.save_photo(entry_id, photo_url)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="回单照片已上传并留存", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条回执单执行登记签收、记录异常、上传回单；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
