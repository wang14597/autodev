from autodev.adapters.event_bus import InMemoryEventBus
from autodev.adapters.sqlite_repository import SqliteWorkItemRepository
from autodev.application.engine import run_until_quiescent
from autodev.application.entrypoints import create_work_item, resume_work_item
from autodev.domain.enums import GatePoint, TaskType
from autodev.domain.enums import WorkflowState as S
from autodev.domain.events import HumanApprovalRequested, WorkItemCompleted, WorkItemCreated
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from tests.conftest import FIXED_NOW


def _dial(*gates):
    return AutonomyDial(frozenset((TaskType.SMALL_CHANGE, "repo-a", g) for g in gates))


def test_end_to_end_with_merge_gate(tmp_path, make_engine):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    bus = InMemoryEventBus()
    seen = []
    bus.subscribe(seen.append)
    eng = make_engine(repo, bus)
    # 只自动 REVIEW_GATE, 保留 MERGE_GATE 人审（切片 1 默认形态）
    wi = create_work_item(
        repo,
        bus,
        work_item_id=WorkItemId.new(),
        repo_ref=RepoRef("repo-a"),
        requirement=Requirement(
            "fix passwrod typo", "repo-a", ("error message spelled correctly",), "raw"
        ),
        autonomy_dial=_dial(GatePoint.REVIEW_GATE),
        now=FIXED_NOW,
        autonomy_enabled=True,
    )

    run_until_quiescent(repo, eng)
    mid = repo.get(wi.id)
    assert mid.state is S.WAIT_HUMAN and mid.pending_gate is GatePoint.MERGE_GATE
    assert {"triage", "context", "design", "review", "impl", "accept", "verify", "delivery"} <= set(
        mid.artifacts
    )
    assert any(isinstance(e, WorkItemCreated) for e in seen)
    assert any(isinstance(e, HumanApprovalRequested) for e in seen)

    resume_work_item(wi.id, True, repo, eng, FIXED_NOW)
    done = repo.get(wi.id)
    assert done.state is S.DONE
    assert done.artifacts["delivery"].change_request_url
    assert any(isinstance(e, WorkItemCompleted) for e in seen)


def test_end_to_end_fully_autonomous(tmp_path, make_engine):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    bus = InMemoryEventBus()
    eng = make_engine(repo, bus)
    wi = create_work_item(
        repo,
        bus,
        work_item_id=WorkItemId.new(),
        repo_ref=RepoRef("repo-a"),
        requirement=Requirement("fix typo", "repo-a", (), "raw"),
        autonomy_dial=_dial(GatePoint.REVIEW_GATE, GatePoint.MERGE_GATE),
        now=FIXED_NOW,
        autonomy_enabled=True,
    )
    run_until_quiescent(repo, eng)
    assert repo.get(wi.id).state is S.DONE
    assert eng.ctx.workspace.cleaned  # DONE 时清理 worktree


def test_end_to_end_verify_failure_fails_cleanly(tmp_path, make_engine):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    bus = InMemoryEventBus()
    eng = make_engine(repo, bus, verify_ok=False)
    wi = create_work_item(
        repo,
        bus,
        work_item_id=WorkItemId.new(),
        repo_ref=RepoRef("repo-a"),
        requirement=Requirement("fix typo", "repo-a", (), "raw"),
        autonomy_dial=_dial(GatePoint.REVIEW_GATE, GatePoint.MERGE_GATE),
        now=FIXED_NOW,
        autonomy_enabled=True,
    )
    run_until_quiescent(repo, eng)
    assert repo.get(wi.id).state is S.FAILED  # VERIFY 反复回退 IMPL 至上限后干净失败
