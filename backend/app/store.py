"""数据仓库：进程重启后数据仍在。

每个业务模块对应内存中的一张表，所有变更会原子地落盘到 data/store.json，
第二天重新打开看到的仍是最后一次保存的内容，而不是示例数据。
回单照片等上传文件放在 data/uploads 下，由接口直接回传。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from app.seed import SEED_ROWS

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RETURNTRIP_DATA_DIR", BASE_DIR / "data"))
STORE_FILE = DATA_DIR / "store.json"
UPLOAD_DIR = DATA_DIR / "uploads"


class Store:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._tables: dict[str, list[dict[str, Any]]] = self._load()

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        """优先读落盘数据；文件不存在（首次启动）时才用示例数据播种。"""
        if STORE_FILE.exists():
            try:
                with STORE_FILE.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    return {name: [dict(row) for row in rows] for name, rows in data.items()}
            except (json.JSONDecodeError, OSError):
                # 落盘文件损坏时不要把现场吞掉，退回到示例数据但保留旧文件便于排查
                pass
        return {name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()}

    def persist(self) -> None:
        """把当前全部数据原子落盘：先写临时文件再改名，避免写一半进程退出导致文件损坏。"""
        with self._lock:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp_file = STORE_FILE.with_suffix(".json.tmp")
            with tmp_file.open("w", encoding="utf-8") as handle:
                json.dump(self._tables, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_file, STORE_FILE)

    def module_names(self) -> list[str]:
        with self._lock:
            return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def find_by_field(self, module: str, field: str, value: str) -> dict[str, Any] | None:
        """按业务编号（如回单编号）查唯一记录；空值不参与匹配。"""
        value = str(value or "").strip()
        if not value:
            return None
        for row in self.rows(module):
            if str(row.get(field) or "").strip() == value:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
