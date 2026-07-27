"""确定性演示适配器 —— 仅供独立演示组合根 / agent-browser E2E 使用。

铁律合规：这些是端口协议的**确定性**实现，无网络、无 AI、无外部 SDK，放 `adapters/`。
生产组合根（`webapp/config.py`）**绝不**注入它们——生产对 DESIGN 及之后仍用抛错桩
（`UnavailableStage`）。演示适配器让控制台可完整驱动生命周期，从而可端到端验证
真实的 `TriagePolicy` / `GatePolicy`（这两者在演示里用真实实现，正是被测对象）。
"""

from __future__ import annotations

from pathlib import Path

from autodev.domain.artifacts import (
    AcceptanceArtifact,
    ContextArtifact,
    DeliveryArtifact,
    DesignArtifact,
    ImplArtifact,
    ReviewArtifact,
    VerificationArtifact,
)
from autodev.domain.enums import GatePoint, TaskType, WorkspaceMode
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import (
    AutonomyDial,
    RepoRef,
    RepoStatus,
    Requirement,
    Verdict,
    WorkspaceHandle,
)


def release_all_dial(repo_name: str) -> AutonomyDial:
    """构造对指定 repo 名的**全部** (TaskType, GatePoint) 组合放行的 AutonomyDial。

    必须按运行时 repo 名动态构造：`needs_human` 按三元组精确匹配，硬编码固定名会导致
    换项目名后命中不了、低风险项照停 WAIT_HUMAN。放行后，唯一还能把工作项挡在人审的
    就是**风险信号**（GatePolicy），这正是要演示的差异化。
    """
    return AutonomyDial(frozenset((t, repo_name, g) for t in TaskType for g in GatePoint))


class DemoWorkspace:
    """确定性 WorkspacePort：不打真实 git，建项/CONTEXT 零外部依赖。"""

    _BRANCH = "main"
    _BRANCHES = ("main", "develop")

    def repo_status(self, repo: RepoRef) -> RepoStatus:
        return RepoStatus(exists_local=True, exists_remote=True)

    def provision(
        self,
        work_item_id: WorkItemId,
        repo: RepoRef,
        mode: WorkspaceMode,
        branch: str,
        base_branch: str | None = None,
    ) -> WorkspaceHandle:
        return WorkspaceHandle(f"/tmp/autodev-demo/{repo.name}/{work_item_id.value[:8]}", branch)

    def cleanup(self, handle: WorkspaceHandle) -> None:
        # no-op —— 但必须存在：engine._finalize_done 在 DONE 时会调用它。
        return None

    def prepare(self, repo: RepoRef, branch: str | None = None) -> str:
        return branch or self._BRANCH

    def list_branches(self, repo: RepoRef) -> list[str]:
        return list(self._BRANCHES)


class DemoContext:
    """确定性 ContextPort：写一个真实临时 Markdown，使控制台简报非空。"""

    def __init__(self, autodev_home: Path) -> None:
        self._home = autodev_home

    def gather(self, requirement: Requirement, handle: WorkspaceHandle) -> ContextArtifact:
        item_dir = self._home / "demo-context"
        item_dir.mkdir(parents=True, exist_ok=True)
        # 文件名基于 handle.label（分支名，如 "autodev/1a8a0768"）；分支名含 "/"，
        # 须净化成扁平文件名，否则会当成不存在的子目录导致写入失败。
        safe = handle.label.replace("/", "_")
        path = item_dir / f"context-{safe}.md"
        path.write_text(
            f"# 上下文简报（演示）\n\n- 目标：{requirement.goal}\n- 分支：{handle.label}\n",
            encoding="utf-8",
        )
        return ContextArtifact(handle.location, handle.label, str(path))


class DemoDesign:
    def propose(self, requirement: Requirement, context: ContextArtifact) -> DesignArtifact:
        return DesignArtifact(f"（演示方案）实现：{requirement.goal}", ("app.py",))


class DemoReview:
    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact:
        return ReviewArtifact(approved=True, comments=("（演示）评审通过",))


class DemoExecution:
    def implement(self, design: DesignArtifact, handle: WorkspaceHandle) -> ImplArtifact:
        return ImplArtifact("--- 演示 diff ---", True, "（演示）已实现")


class DemoVerification:
    def verify(self, criteria: AcceptanceArtifact, handle: WorkspaceHandle) -> VerificationArtifact:
        return VerificationArtifact(Verdict(True, ()), ("（演示）测试通过",))


class DemoDelivery:
    def submit(
        self, requirement: Requirement, design: DesignArtifact, handle: WorkspaceHandle
    ) -> DeliveryArtifact:
        return DeliveryArtifact(f"https://demo.autodev/mr/{handle.label}", handle.label)
