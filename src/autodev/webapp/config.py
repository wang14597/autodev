# src/autodev/webapp/config.py
"""组合根：从环境变量装配真实适配器(F1 workspace/F3 context)+ 桩(DESIGN 及之后)。

只在这里把 driving adapter(FastAPI) 与领域引擎/真实端口接起来；不引入任何新的领域
概念，只是接线。
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from autodev.adapters.claude_runner import ClaudeCodeRunner
from autodev.adapters.context_claude import ClaudeContextAdapter
from autodev.adapters.event_bus import InMemoryEventBus
from autodev.adapters.sqlite_repository import SqliteWorkItemRepository
from autodev.adapters.workspace_git import GitWorkspaceAdapter, GitWorkspaceConfig
from autodev.application.context import StageContext
from autodev.application.engine import Engine
from autodev.domain.policies import GatePolicy, TriagePolicy
from autodev.webapp.app import create_app
from autodev.webapp.service import WorkItemConsoleService
from autodev.webapp.stubs import UnavailableStage


class ThreadPoolExecutorAdapter:
    """`Executor` 协议的线程池实现: `submit` 把驱动循环丢给后台线程执行。"""

    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn: Callable[[], None]) -> None:
        self._pool.submit(fn)


def _load_repo_map(raw: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AUTODEV_REPO_MAP 不是合法 JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("AUTODEV_REPO_MAP 必须是 JSON 对象(name -> url)")
    for name, url in parsed.items():
        if not isinstance(name, str) or not isinstance(url, str):
            raise ValueError("AUTODEV_REPO_MAP 的键值都必须是字符串")
    return parsed


def build_app_from_env() -> FastAPI:
    home = Path(os.environ.get("AUTODEV_HOME", str(Path.home() / ".autodev"))).expanduser()
    home.mkdir(parents=True, exist_ok=True)

    repo_map = _load_repo_map(os.environ.get("AUTODEV_REPO_MAP", "{}"))
    mirror_dir = Path(os.environ.get("AUTODEV_MIRROR_DIR", str(home / "mirrors")))
    workspaces_dir = Path(os.environ.get("AUTODEV_WORKSPACES_DIR", str(home / "workspaces")))

    repo = SqliteWorkItemRepository(str(home / "console.sqlite3"))
    publisher = InMemoryEventBus()

    workspace = GitWorkspaceAdapter(GitWorkspaceConfig(repo_map, mirror_dir, workspaces_dir))
    runner = ClaudeCodeRunner()
    gatherer = ClaudeContextAdapter(runner=lambda p, c: runner.run(p, c), autodev_home=home)
    stub = UnavailableStage()

    ctx = StageContext(
        workspace,
        gatherer,
        stub,
        stub,
        stub,
        stub,
        stub,
        TriagePolicy(),
        GatePolicy(),
    )
    engine = Engine(repo, publisher, ctx, clock=lambda: datetime.now(UTC))
    executor = ThreadPoolExecutorAdapter()
    service = WorkItemConsoleService(repo, engine, executor)

    return create_app(service, projects=sorted(repo_map))
