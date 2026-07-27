# src/autodev/webapp/app.py
"""FastAPI 驱动侧适配器：项目为中心的控制台 HTTP 路由 + 前端产物托管(SPA 回退)。

路由分两层：
- `/api/*`：JSON API，全部在 catch-all 之前注册，永不被其遮蔽。
- 其余路径：若存在前端构建产物(`frontend/dist` 或 `AUTODEV_FRONTEND_DIST`)，
  注册 catch-all 做 SPA 托管(未知路由回退 index.html，防路径穿越)；否则仅
  `GET /` 返回一个占位页。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from autodev.domain.project import Project
from autodev.domain.work_item import WorkItem
from autodev.webapp.views import view_detail, view_project, view_project_detail

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ConsoleService(Protocol):
    """`ProjectConsoleService` 的最小结构化契约, 供路由依赖注入使用。"""

    def create_project(self, name: str, repo_input: str, branch: str = "") -> str: ...

    def list_projects(self) -> list[tuple[Project, int]]: ...

    def get_project(self, project_id: str) -> Project | None: ...

    def refresh_project(self, project_id: str) -> str: ...

    def delete_project(self, project_id: str) -> bool: ...

    def list_branches(self, project_id: str) -> list[str]: ...

    def set_project_branch(self, project_id: str, branch: str) -> str: ...

    def create_workitem(self, project_id: str, goal: str) -> str: ...

    def list_workitems(self, project_id: str) -> list[WorkItem]: ...

    def get_workitem(self, work_item_id: str) -> WorkItem | None: ...

    def approve_workitem(self, work_item_id: str, approved: bool = True) -> WorkItem | None: ...


class CreateProjectRequest(BaseModel):
    name: str
    repo: str
    branch: str = ""


class CreateWorkItemRequest(BaseModel):
    goal: str


class SetBranchRequest(BaseModel):
    branch: str


class ApproveRequest(BaseModel):
    approved: bool = True


def _frontend_dist() -> Path | None:
    """返回前端构建产物目录, 若不存在(未构建)则返回 None。"""
    env = os.environ.get("AUTODEV_FRONTEND_DIST")
    candidate = Path(env) if env else Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return candidate if (candidate / "index.html").is_file() else None


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def create_app(service: ConsoleService) -> FastAPI:
    app = FastAPI(title="AutoDev 项目控制台")

    @app.get("/api/projects")
    def get_projects() -> list[dict[str, object]]:
        return [view_project(p, count) for (p, count) in service.list_projects()]

    @app.post("/api/projects")
    def create_project(payload: CreateProjectRequest) -> dict[str, str]:
        try:
            project_id = service.create_project(payload.name, payload.repo, payload.branch)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"id": project_id}

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, object]:
        project = service.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return view_project_detail(project, service.list_workitems(project_id))

    @app.post("/api/projects/{project_id}/refresh")
    def refresh_project(project_id: str) -> dict[str, str]:
        try:
            branch = service.refresh_project(project_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail="project not found") from e
        return {"branch": branch}

    @app.get("/api/projects/{project_id}/branches")
    def get_project_branches(project_id: str) -> list[str]:
        try:
            return service.list_branches(project_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail="project not found") from e

    @app.post("/api/projects/{project_id}/branch")
    def set_project_branch(project_id: str, payload: SetBranchRequest) -> dict[str, str]:
        try:
            branch = service.set_project_branch(project_id, payload.branch)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except LookupError as e:
            raise HTTPException(status_code=404, detail="project not found") from e
        return {"branch": branch}

    @app.delete("/api/projects/{project_id}")
    def delete_project(project_id: str) -> dict[str, bool]:
        if not service.delete_project(project_id):
            raise HTTPException(status_code=404, detail="project not found")
        return {"deleted": True}

    @app.post("/api/projects/{project_id}/workitems")
    def create_workitem(project_id: str, payload: CreateWorkItemRequest) -> dict[str, str]:
        try:
            work_item_id = service.create_workitem(project_id, payload.goal)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except LookupError as e:
            raise HTTPException(status_code=404, detail="project not found") from e
        return {"id": work_item_id}

    @app.get("/api/workitems/{work_item_id}")
    def get_workitem(work_item_id: str) -> dict[str, object]:
        wi = service.get_workitem(work_item_id)
        if wi is None:
            raise HTTPException(status_code=404, detail="work item not found")
        return view_detail(wi, _read_text)

    @app.post("/api/workitems/{work_item_id}/approve")
    def approve_workitem(work_item_id: str, payload: ApproveRequest) -> dict[str, object]:
        try:
            wi = service.approve_workitem(work_item_id, payload.approved)
        except Exception as e:  # noqa: BLE001 领域不变式（非 WAIT_HUMAN 等）→ 400
            raise HTTPException(status_code=400, detail=str(e)) from e
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
