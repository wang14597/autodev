"""独立演示组合根 —— 仅供 demo / agent-browser E2E，**生产入口绝不引用本模块**。

与生产组合根（`config.py`）刻意分开：演示注入确定性演示适配器 + 放行 dial + 全生命周期
驱动，用真实 `TriagePolicy`/`GatePolicy`（被测对象）。这样一个误设的环境变量无法让假
适配器对真实用户服务——安全立场"沙箱是真实执行硬前置"从结构上得到保证。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from autodev.adapters.demo import (
    DemoContext,
    DemoDelivery,
    DemoDesign,
    DemoExecution,
    DemoReview,
    DemoVerification,
    DemoWorkspace,
    FakeTriage,
    release_all_dial,
)
from autodev.adapters.event_bus import InMemoryEventBus
from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.adapters.project_repository import InMemoryProjectRepository
from autodev.application.context import StageContext
from autodev.application.engine import Engine
from autodev.domain.policies import GatePolicy
from autodev.webapp.app import create_app
from autodev.webapp.drive import ALL_STAGES
from autodev.webapp.projects import ProjectRegistry
from autodev.webapp.service import ProjectConsoleService, SyncExecutor


def build_demo_app() -> FastAPI:
    """装配确定性演示控制台：内存仓储 + 演示适配器 + 真实 Triage/Gate + 放行 dial。

    用 `SyncExecutor` 使驱动同步完成——create_workitem 返回时状态已定（DONE/WAIT_HUMAN），
    E2E 轮询立即可见，无并发时序抖动。
    """
    home = Path(os.environ.get("AUTODEV_HOME", str(Path.home() / ".autodev-demo"))).expanduser()
    home.mkdir(parents=True, exist_ok=True)

    work_repo = InMemoryWorkItemRepository()
    project_repo = InMemoryProjectRepository()
    workspace = DemoWorkspace()
    ctx = StageContext(
        workspace,
        DemoContext(autodev_home=home),
        DemoDesign(),
        DemoReview(),
        DemoExecution(),
        DemoVerification(),
        DemoDelivery(),
        FakeTriage(),
        GatePolicy(),
    )
    engine = Engine(work_repo, InMemoryEventBus(), ctx, clock=lambda: datetime.now(UTC))
    registry = ProjectRegistry({}, home / "repos.json")
    service = ProjectConsoleService(
        project_repo,
        work_repo,
        workspace,
        engine,
        SyncExecutor(),
        registry,
        dial_factory=release_all_dial,
        implemented_stages=ALL_STAGES,
    )
    return create_app(service)
