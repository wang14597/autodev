# tests/application/test_engine.py
from datetime import datetime

from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.application.context import StageContext
from autodev.application.engine import Engine, run_until_quiescent
from autodev.domain.artifacts import DesignArtifact, ReviewArtifact
from autodev.domain.enums import GatePoint, TaskType
from autodev.domain.enums import WorkflowState as S
from autodev.domain.events import HumanApprovalRequested, WorkItemFailed
from autodev.domain.ids import WorkItemId
from autodev.domain.policies import GatePolicy
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem
from tests.fakes import (
    FakeContext,
    FakeDelivery,
    FakeDesign,
    FakeExecution,
    FakeReview,
    FakeTriage,
    FakeVerification,
    FakeWorkspace,
    RecordingPublisher,
)

NOW = datetime(2026, 7, 15)


def _engine(repo, pub, review_ok=True, verify_ok=True):
    ctx = StageContext(
        workspace=FakeWorkspace(local=True),
        gatherer=FakeContext(),
        designer=FakeDesign(),
        reviewer=FakeReview(approved=review_ok),
        executor=FakeExecution(),
        verifier=FakeVerification(passed=verify_ok),
        delivery=FakeDelivery(),
        triage=FakeTriage(),
        gate_policy=GatePolicy(),
    )
    return Engine(repo, pub, ctx, clock=lambda: NOW)


def _wi(dial):
    return WorkItem.create(
        WorkItemId.new(),
        RepoRef("repo-a"),
        Requirement("fix typo", "repo-a", (), "raw"),
        dial,
        NOW,
        autonomy_enabled=True,  # 引擎驱动测试需流过 CONTEXT（否则默认停 CONTEXT_GATE）
    )


def test_stage_failure_is_logged_with_kind_and_next_action(caplog):
    """阶段失败必须留下一行日志——含阶段、失败类型、原因、以及接下来干什么。

    没有它，一次跑了十几分钟又失败的阶段在平台侧不留任何痕迹：实测中评审阶段连续
    两次被超时杀掉，只能靠 claude CLI 自己的会话文件才还原出时间线，平台日志里
    只有 HTTP 行。判别性：去掉日志调用则 caplog 为空。
    """
    import logging

    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    wi = _wi(dial)
    repo.save(wi)
    with caplog.at_level(logging.WARNING, logger="autodev.application.engine"):
        run_until_quiescent(repo, _engine(repo, pub, review_ok=False))

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "REVIEW" in text  # 哪个阶段
    assert "LOGIC" in text  # 失败类型
    assert "rollback" in text or "fail" in text  # 接下来干什么
    assert str(wi.id.value) in text  # 哪个工作项


def test_runs_until_merge_gate_suspend():
    # REVIEW_GATE 自动、MERGE_GATE 人审
    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    wi = _wi(dial)
    repo.save(wi)
    run_until_quiescent(repo, _engine(repo, pub))
    got = repo.get(wi.id)
    assert got.state is S.WAIT_HUMAN and got.pending_gate is GatePoint.MERGE_GATE
    assert any(isinstance(e, HumanApprovalRequested) for e in pub.events)
    assert "delivery" in got.artifacts


def test_verify_failure_rolls_back_and_eventually_fails():
    dial = AutonomyDial(
        frozenset(
            {
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE),
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE),
            }
        )
    )
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    eng = _engine(repo, pub, verify_ok=False)
    wi = _wi(dial)
    repo.save(wi)
    run_until_quiescent(repo, eng)
    got = repo.get(wi.id)
    assert got.state is S.FAILED
    assert any(isinstance(e, WorkItemFailed) for e in pub.events)
    assert eng.ctx.executor.calls == 4
    assert len(got.versions_of("impl")) == 4


def test_transient_failure_retries_then_succeeds():
    from autodev.domain.artifacts import ContextArtifact

    class FlakyContext:
        def __init__(self, fail_times):
            self.fail_times = fail_times
            self.calls = 0

        def gather(self, requirement, handle):
            self.calls += 1
            if self.calls <= self.fail_times:
                raise RuntimeError("transient blip")
            return ContextArtifact(handle.location, handle.label, f"{handle.location}/context.md")

    dial = AutonomyDial(
        frozenset(
            {
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE),
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE),
            }
        )
    )
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    eng = _engine(repo, pub)
    eng.ctx.gatherer = FlakyContext(fail_times=2)  # fail twice, succeed on 3rd
    wi = _wi(dial)
    repo.save(wi)
    run_until_quiescent(repo, eng)
    got = repo.get(wi.id)
    assert got.state is S.DONE  # recovered after retries
    assert got.retry_ledger.count("CONTEXT:transient") == 2
    assert eng.ctx.gatherer.calls == 3


def test_fully_auto_reaches_done_and_cleans_up():
    dial = AutonomyDial(
        frozenset(
            {
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE),
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE),
            }
        )
    )
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()
    eng = _engine(repo, pub)
    wi = _wi(dial)
    repo.save(wi)
    run_until_quiescent(repo, eng)
    got = repo.get(wi.id)
    assert got.state is S.DONE
    assert eng.ctx.workspace.cleaned  # cleanup 被调用


def test_rejected_review_is_persisted_so_redesign_sees_prior_review():
    """Critical（编排者核实的跨任务缺陷）：handle_review 判回退时必须先把评审产物落到
    工作项上。engine._on_failure 从不 add_artifact（只有 _on_success/_on_suspend/
    _on_finish 会落产物），若 handle_review 不自己落盘，回退到 DESIGN 后
    handle_design 从 work_item.artifacts.get("review") 永远只能取到 None —— Task 2
    打通的 prior_review 通道形同虚设，回退重设计的死结（同样输入产同样方案、同样
    被打回、烧完 CAP 收敛 FAILED）依然存在，只是没暴露。

    判别性：退回"handle_review 判回退时不落盘直接 fail"的旧实现，设计端口第二次
    收到的 prior_review 会是 None 而不是那份被否的 ReviewArtifact，断言失败。
    """
    dial = AutonomyDial(
        frozenset(
            {
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE),
                (TaskType.SMALL_CHANGE, "repo-a", GatePoint.MERGE_GATE),
            }
        )
    )
    repo, pub = InMemoryWorkItemRepository(), RecordingPublisher()

    rejected = ReviewArtifact(False, ("- blocking: 方案方向不对",))

    class FlakyReview:
        """判回退一次、再通过——用于验证回退重设计确实用上了上一轮意见。"""

        def __init__(self):
            self.calls = 0

        def review(self, design, context):
            self.calls += 1
            return rejected if self.calls == 1 else ReviewArtifact(True, ())

    class RecordingDesign:
        def __init__(self):
            self.seen_prior_reviews: list[object] = []

        def propose(self, requirement, context, prior_review=None):
            self.seen_prior_reviews.append(prior_review)
            return DesignArtifact(design_file=f"/x/design-{len(self.seen_prior_reviews)}.md")

    recording_design = RecordingDesign()
    ctx = StageContext(
        workspace=FakeWorkspace(local=True),
        gatherer=FakeContext(),
        designer=recording_design,
        reviewer=FlakyReview(),
        executor=FakeExecution(),
        verifier=FakeVerification(passed=True),
        delivery=FakeDelivery(),
        triage=FakeTriage(),
        gate_policy=GatePolicy(),
    )
    eng = Engine(repo, pub, ctx, clock=lambda: NOW)
    wi = _wi(dial)
    repo.save(wi)

    run_until_quiescent(repo, eng)

    got = repo.get(wi.id)
    assert got.state is S.DONE  # 回退一次后仍应恢复、跑到底（未被误伤收敛 FAILED）
    assert recording_design.seen_prior_reviews == [None, rejected]
