from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from autodev.domain.artifacts import TriageArtifact
from autodev.domain.enums import (
    FailureKind,
    GatePoint,
    RiskLevel,
    TaskType,
    TriageIntent,
    WorkflowState,
    WorkspaceMode,
)
from autodev.domain.enums import (
    WorkflowState as S,
)
from autodev.domain.errors import InvariantError
from autodev.domain.value_objects import GateDecision, RepoStatus, Requirement, RetryLedger
from autodev.domain.work_item import WorkItem

# 高风险关键词：触碰安全/凭证/破坏性操作 → 抬升风险等级。
_HIGH_RISK_WORDS = (
    "delete",
    "drop",
    "migrate",
    "security",
    "auth",
    "payment",
    "credential",
    "secret",
    "token",
    "permission",
    "encrypt",
)
# 低风险/琐碎关键词：文档/注释/重命名/拼写 → 降风险、判 SMALL_CHANGE。
_LOW_RISK_WORDS = ("typo", "rename", "comment", "doc", "docs", "readme", "changelog")
# 规模关键词：跨模块/多服务/重构 → 抬升任务类型。
_SCOPE_WORDS = ("across", "multiple", "modules", "services", "refactor", "subsystem", "end-to-end")


def _hits(text: str, words: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(w for w in words if w in text)


class TriagePolicy:
    """确定性启发式分诊：仅凭需求文本 + 仓库状态，无网络/无 AI，保证可重复。

    产出 TaskType（规模）、confidence（把握度）、RiskLevel（风险）与可解释 signals。
    端口签名不变，未来可替换为 AI 分诊而不动调用方。
    """

    def triage(self, requirement: Requirement, status: RepoStatus) -> TriageArtifact:
        if status.exists_local:
            mode = WorkspaceMode.REUSE
        elif status.exists_remote:
            mode = WorkspaceMode.FETCH
        else:
            mode = WorkspaceMode.CREATE

        text = f"{requirement.goal} {requirement.raw_text}".lower()
        signals: list[str] = []

        high = _hits(text, _HIGH_RISK_WORDS)
        low = _hits(text, _LOW_RISK_WORDS)
        scope = _hits(text, _SCOPE_WORDS)
        signals += [f"keyword:{w}" for w in high]
        signals += [f"trivial:{w}" for w in low]
        signals += [f"scope:{w}" for w in scope]

        # 风险：命中高风险词 → HIGH；纯低风险词 → LOW；否则 MEDIUM。
        if high:
            risk = RiskLevel.HIGH
        elif low and not scope:
            risk = RiskLevel.LOW
        else:
            risk = RiskLevel.MEDIUM

        # 任务类型：规模词或多高风险词 → 更大类型；纯琐碎 → SMALL_CHANGE。
        if len(scope) >= 2 or (scope and high):
            level = TaskType.COMPLEX_FEATURE
        elif scope or len(high) >= 2:
            level = TaskType.MEDIUM_FEATURE
        else:
            level = TaskType.SMALL_CHANGE

        # 置信度：有验收提示 + 目标够具体 → 高；含糊（既短又无任何可识别关键词）→ 低。
        # 注意"短"≠"含糊"："fix typo" 虽短但含琐碎关键词，属清晰任务，不罚。
        recognized = bool(high or low or scope)
        confidence = 0.9
        if not requirement.acceptance_hints:
            confidence -= 0.2
        if len(requirement.goal.split()) < 3 and not recognized:
            confidence -= 0.25
            signals.append("vague:short-goal")
        confidence = max(0.1, min(1.0, confidence))

        return TriageArtifact(
            level=level,
            confidence=confidence,
            workspace_mode=mode,
            risk=risk,
            signals=tuple(signals),
        )


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

    返回 "suspend"（挂起 CONTEXT_GATE 交人）/ "finish"（仅收集完成→DONE）/ "proceed"（继续 DESIGN）。
    规则严格按序早返回：分诊失败/低置信永不被 autonomy_enabled 跳过。置信下限复用
    GatePolicy.CONFIDENCE_GATE_THRESHOLD 单一真源。
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
