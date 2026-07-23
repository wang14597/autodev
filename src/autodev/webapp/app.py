# src/autodev/webapp/app.py
"""FastAPI 驱动侧适配器：WorkItem 控制台 HTTP 路由 + 前端产物托管(SPA 回退)。

路由分两层：
- `/api/*`：JSON API，全部在 catch-all 之前注册，永不被其遮蔽。
- 其余路径：若存在前端构建产物(`frontend/dist` 或 `AUTODEV_FRONTEND_DIST`)，
  注册 catch-all 做 SPA 托管(未知路由回退 index.html，防路径穿越)；否则仅
  `GET /` 返回一个占位页。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from autodev.domain.work_item import WorkItem
from autodev.webapp.views import view_detail, view_summary

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ConsoleService(Protocol):
    """`WorkItemConsoleService` 的最小结构化契约, 供路由依赖注入使用。"""

    def create(self, goal: str, repo: str) -> str: ...

    def get(self, work_item_id: str) -> WorkItem | None: ...

    def list(self) -> list[WorkItem]: ...


class CreateWorkItemRequest(BaseModel):
    goal: str
    repo: str


def _frontend_dist() -> Path | None:
    """返回前端构建产物目录, 若不存在(未构建)则返回 None。"""
    env = os.environ.get("AUTODEV_FRONTEND_DIST")
    candidate = Path(env) if env else Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return candidate if (candidate / "index.html").is_file() else None


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def create_app(
    service: ConsoleService,
    projects: list[str] | Callable[[], list[str]],
) -> FastAPI:
    app = FastAPI(title="AutoDev WorkItem 控制台")

    @app.get("/api/projects")
    def get_projects() -> list[str]:
        # projects 可为静态列表或 provider(登记表运行时会新增本地项目, 故用 provider 取最新)。
        return projects() if callable(projects) else projects

    @app.post("/api/workitems")
    def create_workitem(payload: CreateWorkItemRequest) -> dict[str, str]:
        try:
            work_item_id = service.create(payload.goal, payload.repo)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"id": work_item_id}

    @app.get("/api/workitems")
    def list_workitems() -> list[dict[str, object]]:
        return [view_summary(wi) for wi in service.list()]

    @app.get("/api/workitems/{work_item_id}")
    def get_workitem(work_item_id: str) -> dict[str, object]:
        wi = service.get(work_item_id)
        if wi is None:
            raise HTTPException(status_code=404, detail="work item not found")
        return view_detail(wi, _read_text)

    dist = _frontend_dist()
    if dist is not None:
        _mount_spa(app, dist)
    else:

        @app.get("/")
        def placeholder() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """挂载 SPA catch-all：dist 内真实文件直接回, 其余(未知前端路由)回退 index.html。

    注册顺序在 `/api/*` 之后 —— FastAPI/Starlette 按注册顺序匹配路由, 因此 `/api`
    请求永远先命中上面的具体路由, 不会落进这个 catch-all。
    """
    dist_resolved = dist.resolve()
    index_file = dist / "index.html"

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        candidate = (dist / full_path).resolve()
        if candidate.is_file() and dist_resolved in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index_file)
