"""数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

进程启动时优先读取 data/store.json 里的持久化快照；任何登记、编辑、动作落库后
通过 save() 原子写回磁盘。这样第二天重启服务，签收方、签收日期、异常备注、
回单照片这些改动仍然挂在原来的回单编号上，不会被示例种子数据覆盖。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Any

from app.seed import SEED_ROWS

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SNAPSHOT_PATH = os.path.join(DATA_DIR, "store.json")


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tables = self._load()

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        """优先用磁盘快照恢复数据；快照缺失或损坏时回退到种子数据。"""
        try:
            with open(SNAPSHOT_PATH, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            tables = {
                name: [dict(row) for row in rows]
                for name, rows in data.items()
                if isinstance(rows, list)
            }
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            tables = {}
        # 种子里新增的模块也要能在旧快照上补齐，但绝不覆盖已经改过的数据。
        for name, rows in SEED_ROWS.items():
            tables.setdefault(name, [dict(row) for row in rows])
        return tables

    def save(self) -> None:
        """把当前全量数据原子落盘：先写临时文件再替换，避免写一半导致历史记录损坏。"""
        os.makedirs(DATA_DIR, exist_ok=True)
        with self._lock:
            snapshot = json.dumps(self._tables, ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(prefix="store-", suffix=".tmp", dir=DATA_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(snapshot)
            os.replace(tmp_path, SNAPSHOT_PATH)
        except OSError:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def find_by(self, module: str, field: str, value: Any) -> dict[str, Any] | None:
        """按业务编号（例如回单编号）定位记录，保证改动只落在对应的那一条上。"""
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        for row in self.rows(module):
            if str(row.get(field, "")).strip() == text:
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
