from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from autodev.domain.artifacts import TriageArtifact
from autodev.domain.enums import (
    FailureKind,
    GatePoint,
    RiskLevel,
    TriageIntent,
    WorkflowState,
    WorkspaceMode,
)
from autodev.domain.enums import (
    WorkflowState as S,
)
from autodev.domain.errors import InvariantError
from autodev.domain.value_objects import GateDecision, RepoStatus, RetryLedger
from autodev.domain.work_item import WorkItem


def workspace_mode_for(status: RepoStatus) -> WorkspaceMode:
    """从仓库状态推出工作区模式（机械判断，不归 LLM 分诊）。"""
    if status.exists_local:
        return WorkspaceMode.REUSE
    if status.exists_remote:
        return WorkspaceMode.FETCH
    return WorkspaceMode.CREATE


class GatePolicy:
    """风险感知门禁：AutonomyDial 决定"允许自动的上限"，风险信号只能进一步收紧。

    单调性（安全不变式）：`needs_human` = dial 要求 **OR** 风险 HIGH **OR** 置信 < 阈值。
    风险信号绝不放宽 dial —— 放门只会更谨慎，永不因逻辑更激进。
    """

    CONFIDENCE_GATE_THRESHOLD = 0.5

    def decide(self, work_item: WorkItem, gate: GatePoint) -> GateDecision:
        if work_item.type is None:
            return GateDecision(True, "type unknown -> require human")
        dial_needs = work_item.autonomy_dial.needs_human(
            work_item.type, work_item.repo_ref.name, gate
        )
        triage_obj = work_item.artifacts.get("triage")
        if triage_obj is None:
            return GateDecision(dial_needs, "per autonomy dial")
        triage = cast(TriageArtifact, triage_obj)

        high_risk = triage.risk is RiskLevel.HIGH
        low_conf = triage.confidence < self.CONFIDENCE_GATE_THRESHOLD
        # OR 单调：任一收紧条件成立即需人审；不得清除 dial_needs。
        needs = dial_needs or high_risk or low_conf
        reasons = []
        if dial_needs:
            reasons.append("dial")
        if high_risk:
            reasons.append("risk=HIGH")
        if low_conf:
            reasons.append(f"confidence<{self.CONFIDENCE_GATE_THRESHOLD}")
        reason = " | ".join(reasons) if needs else "auto (dial + low risk)"
        return GateDecision(needs, reason)


class AutonomyPolicy:
    """上下文收集后的「是否继续」决策（安全兜底优先于开关与意图）。

    返回 "suspend"（挂起 CONTEXT_GATE 交人）/ "finish"（仅收集完成→DONE）/
    "proceed"（继续 DESIGN）。规则严格按序早返回：分诊失败/低置信永不被
    autonomy_enabled 跳过。置信下限复用 GatePolicy.CONFIDENCE_GATE_THRESHOLD 单一真源。
    """

    def decide_after_context(self, work_item: WorkItem) -> str:
        triage_obj = work_item.artifacts.get("triage")
        # 规则 1（安全兜底）：无分诊 / 不可用 / 低置信 → 人审（无论开关）。
        if triage_obj is None:
            return "suspend"
        triage = cast(TriageArtifact, triage_obj)
        if (
            "triage-unavailable" in triage.signals
            or triage.confidence < GatePolicy.CONFIDENCE_GATE_THRESHOLD
        ):
            return "suspend"
        # 规则 2：开关关 → 用户决定。
        if not work_item.autonomy_enabled:
            return "suspend"
        # 规则 3：咨询类 → 仅收集完成。
        if triage.intent is TriageIntent.CONSULTATION:
            return "finish"
        # 规则 4：其余 → 继续。
        return "proceed"


_NEXT = {
    S.INTAKE: S.TRIAGE,
    S.TRIAGE: S.CONTEXT,
    S.CONTEXT: S.DESIGN,
    S.DESIGN: S.REVIEW,
    S.REVIEW: S.IMPL,
    S.IMPL: S.ACCEPT,
    S.ACCEPT: S.VERIFY,
    S.VERIFY: S.SUBMIT_MR,
    S.SUBMIT_MR: S.DONE,
}


class TransitionRules:
    def next_state(self, state: WorkflowState) -> WorkflowState:
        if state not in _NEXT:
            raise InvariantError(f"no linear successor for {state.name}")
        return _NEXT[state]


@dataclass(frozen=True)
class RetryDecision:
    action: str  # "retry" | "rollback" | "fail"
    target: WorkflowState | None
    key: str


class RetryPolicy:
    CAP = 3
    ROLLBACK_TARGET = {S.VERIFY: S.IMPL, S.REVIEW: S.DESIGN}

    def decide(
        self, state: WorkflowState, failure_kind: FailureKind, ledger: RetryLedger
    ) -> RetryDecision:
        if failure_kind is FailureKind.FATAL:
            return RetryDecision("fail", None, "")
        if failure_kind is FailureKind.TRANSIENT:
            key = f"{state.name}:transient"
            if ledger.count(key) >= self.CAP:
                return RetryDecision("fail", None, key)
            return RetryDecision("retry", state, key)
        # LOGIC
        target = self.ROLLBACK_TARGET.get(state)
        if target is None:
            return RetryDecision("fail", None, f"{state.name}:logic")
        key = f"{state.name}:logic"
        if ledger.count(key) >= self.CAP:
            return RetryDecision("fail", None, key)
        return RetryDecision("rollback", target, key)
