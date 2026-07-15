from __future__ import annotations

from dataclasses import dataclass

from autodev.domain.enums import FailureKind, GatePoint


@dataclass(frozen=True)
class StageOutcome:
    kind: str
    artifact_key: str | None = None
    artifact: object | None = None
    gate_point: GatePoint | None = None
    failure_kind: FailureKind | None = None
    message: str = ""

    @classmethod
    def ok(cls, artifact_key: str | None = None, artifact: object | None = None) -> StageOutcome:
        return cls("success", artifact_key=artifact_key, artifact=artifact)

    @classmethod
    def suspend(
        cls, gate_point: GatePoint, artifact_key: str | None = None, artifact: object | None = None
    ) -> StageOutcome:
        return cls("suspend", artifact_key=artifact_key, artifact=artifact, gate_point=gate_point)

    @classmethod
    def fail(cls, failure_kind: FailureKind, message: str) -> StageOutcome:
        return cls("failure", failure_kind=failure_kind, message=message)
