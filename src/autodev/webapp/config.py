# src/autodev/webapp/config.py
"""组合根：从环境变量装配真实适配器(F1 workspace/F3 context/F4 design/+ 评审)+ 桩(IMPL 及之后)。

只在这里把 driving adapter(FastAPI) 与领域引擎/真实端口接起来；不引入任何新的领域
概念，只是接线。
"""

from __future__ import annotations

import json
import os
import warnings
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from autodev.adapters.claude_runner import ClaudeCodeRunner
from autodev.adapters.context_claude import ClaudeContextAdapter
from autodev.adapters.design_claude import ClaudeDesignAdapter
from autodev.adapters.event_bus import InMemoryEventBus
from autodev.adapters.project_repository import SqliteProjectRepository
from autodev.adapters.review_claude import ClaudeReviewAdapter
from autodev.adapters.sqlite_repository import SqliteWorkItemRepository
from autodev.adapters.triage_llm import LlmTriageAdapter, _auth_headers_from_env
from autodev.adapters.workspace_git import GitWorkspaceAdapter, GitWorkspaceConfig
from autodev.application.context import StageContext
from autodev.application.engine import Engine
from autodev.domain.policies import GatePolicy
from autodev.webapp.app import create_app
from autodev.webapp.projects import load_registry
from autodev.webapp.service import ProjectConsoleService
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
    return create_app(build_env_service())


def build_env_service() -> ProjectConsoleService:
    home = Path(os.environ.get("AUTODEV_HOME", str(Path.home() / ".autodev"))).expanduser()
    home.mkdir(parents=True, exist_ok=True)

    env_repo_map = _load_repo_map(os.environ.get("AUTODEV_REPO_MAP", "{}"))
    # 登记表：环境变量映射 + 持久化的本地项目(~/.autodev/repos.json)合并; 运行时可自动新增。
    registry = load_registry(env_repo_map, home / "repos.json")
    mirror_dir = Path(os.environ.get("AUTODEV_MIRROR_DIR", str(home / "mirrors")))
    workspaces_dir = Path(os.environ.get("AUTODEV_WORKSPACES_DIR", str(home / "workspaces")))

    repo = SqliteWorkItemRepository(str(home / "console.sqlite3"))
    project_repo = SqliteProjectRepository(str(home / "projects.sqlite3"))
    publisher = InMemoryEventBus()

    # 与登记表共享同一个 repo_map dict, 运行时新增的本地项目对 F1 立即生效。
    workspace = GitWorkspaceAdapter(
        GitWorkspaceConfig(registry.repo_map, mirror_dir, workspaces_dir)
    )
    runner = ClaudeCodeRunner()
    gatherer = ClaudeContextAdapter(runner=lambda p, c: runner.run(p, c), autodev_home=home)
    designer = ClaudeDesignAdapter(runner=lambda p, c: runner.run(p, c), autodev_home=home)
    reviewer = ClaudeReviewAdapter(runner=lambda p, c: runner.run(p, c), autodev_home=home)
    stub = UnavailableStage()

    # 分诊：真实 LLM 分诊(直连 Messages API,Opus 4.8)。缺 key/token 时不 fail-fast——
    # 启动打警告,每次分诊调用将 StageError→降级为挂起人审(平台退化为人工分诊闸,不阻断)。
    if not _auth_headers_from_env():
        warnings.warn(
            "未检测到 LLM 分诊凭据(ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN 等); "
            "分诊将不可用并回退为挂起人审。",
            stacklevel=2,
        )
    triage = LlmTriageAdapter.from_env()
    ctx = StageContext(
        workspace,
        gatherer,
        designer,
        reviewer,
        stub,
        stub,
        stub,
        triage,
        GatePolicy(),
    )
    engine = Engine(repo, publisher, ctx, clock=lambda: datetime.now(UTC))
    executor = ThreadPoolExecutorAdapter()
    return ProjectConsoleService(project_repo, repo, workspace, engine, executor, registry)
