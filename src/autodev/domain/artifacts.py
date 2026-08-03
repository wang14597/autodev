from __future__ import annotations

from dataclasses import dataclass

from autodev.domain.enums import RiskLevel, TaskType, TriageIntent, WorkspaceMode
from autodev.domain.value_objects import Verdict


@dataclass(frozen=True)
class TriageArtifact:
    level: TaskType
    confidence: float
    workspace_mode: WorkspaceMode
    # 风险维度（切片 2.1）：喂给 GatePolicy 做风险感知门禁；signals 为可解释依据。
    # 加默认值保证向后兼容（旧持久化产物、现有构造点无需改）。
    risk: RiskLevel = RiskLevel.LOW
    signals: tuple[str, ...] = ()
    # 意图（LLM 分诊）：ACTIONABLE=需落地改动；CONSULTATION=查询/咨询/仅需求收集。
    # 驱动「上下文后是否继续」的决策（见 AutonomyPolicy）。默认值向后兼容。
    intent: TriageIntent = TriageIntent.ACTIONABLE


@dataclass(frozen=True)
class ContextArtifact:
    workspace_location: str
    workspace_label: str
    context_file: str


@dataclass(frozen=True)
class DesignArtifact:
    design_file: str


@dataclass(frozen=True)
class ReviewArtifact:
    approved: bool
    comments: tuple[str, ...]
    # 评审产出的最终方案文档路径（下游 IMPL 的权威输入）。加默认值向后兼容：
    # 旧持久化产物与演示/假适配器无需同步改造。判定"无法自救"而回退重设计时为空串。
    final_plan_file: str = ""


@dataclass(frozen=True)
class ImplArtifact:
    diff: str
    test_passed: bool
    summary: str


@dataclass(frozen=True)
class AcceptanceArtifact:
    criteria: tuple[str, ...]


@dataclass(frozen=True)
class VerificationArtifact:
    verdict: Verdict
    details: tuple[str, ...]


@dataclass(frozen=True)
class DeliveryArtifact:
    change_request_url: str
    label: str
