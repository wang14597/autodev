# src/autodev/webapp/service.py
"""WorkItem 控制台应用服务：创建 + 有界自动驱动(止于 DESIGN) + 查询。

有界驱动只允许引擎跑 INTAKE/TRIAGE/CONTEXT 三个已实现阶段；一旦 WorkItem 转移到
DESIGN(或任何未实现阶段) 或进入终态/挂起态，驱动循环立即停止，绝不会调用到
DESIGN 及之后的桩端口(见 stubs.py)。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from autodev.application.engine import Engine
from autodev.domain.enums import WorkflowState as S
from autodev.domain.ids import WorkItemId
from autodev.domain.ports import WorkItemRepository
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem

# 有界驱动允许自动跑的阶段集合：仅到 CONTEXT 为止，绝不进入 DESIGN 及之后。
RUN: frozenset[S] = frozenset({S.INTAKE, S.TRIAGE, S.CONTEXT})


def _default_clock() -> datetime:
    return datetime.now(UTC)


class Executor(Protocol):
    def submit(self, fn: Callable[[], None]) -> None: ...


class SyncExecutor:
    """同步执行器：`submit` 立即原地调用，供测试/单进程场景使用。"""

    def submit(self, fn: Callable[[], None]) -> None:
        fn()


class WorkItemConsoleService:
    def __init__(
        self,
        repo: WorkItemRepository,
        engine: Engine,
        executor: Executor,
        clock: Callable[[], datetime] = _default_clock,
        id_gen: Callable[[], WorkItemId] = WorkItemId.new,
    ) -> None:
        self._repo = repo
        self._engine = engine
        self._executor = executor
        self._clock = clock
        self._id_gen = id_gen

    def create(self, goal: str, repo: str) -> str:
        if not goal or not goal.strip():
            raise ValueError("goal must not be empty")
        if not repo or not repo.strip():
            raise ValueError("repo must not be empty")

        work_item_id = self._id_gen()
        requirement = Requirement(goal, repo, (), goal)
        work_item = WorkItem.create(
            work_item_id,
            RepoRef(repo),
            requirement,
            AutonomyDial.all_human(),
            self._clock(),
        )
        self._repo.save(work_item)
        self._executor.submit(lambda: self._drive(work_item_id))
        return work_item_id.value

    def get(self, work_item_id: str) -> WorkItem | None:
        try:
            return self._repo.get(WorkItemId(work_item_id))
        except KeyError:
            return None

    def list(self) -> list[WorkItem]:
        # 从仓库枚举全部工作项(持久化, 进程重启后仍可见), 按创建时间新到旧。
        items = self._repo.list_all()
        items.sort(key=lambda wi: wi.created_at or datetime.min, reverse=True)
        return items

    def _drive(self, work_item_id: WorkItemId) -> None:
        while True:
            try:
                work_item = self._repo.get(work_item_id)
            except KeyError:
                return
            if not work_item.is_runnable() or work_item.state not in RUN:
                return
            self._engine.advance(work_item)
