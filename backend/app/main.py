"""冷链物流运输管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import ROUTERS
from app.store import UPLOAD_DIR, store

app = FastAPI(title="冷链物流运输管理平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def persist_after_mutation(request: Request, call_next):
    """任何写请求（POST/PUT/PATCH/DELETE）处理完且成功后统一落盘。

    业务层只管改内存数据，持久化口径收在这一处，避免某个接口忘记保存
    导致“改完当时对、第二天又回去”的问题。GET 等只读请求不触发落盘。
    """
    response = await call_next(request)
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
        store.persist()
    return response


for module in ROUTERS:
    app.include_router(module.router)


# 回单照片等上传文件以静态目录方式暴露，回单记录里保存的是 /uploads/ 下的相对地址
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()
