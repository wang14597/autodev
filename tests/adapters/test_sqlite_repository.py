from datetime import datetime

from autodev.adapters.sqlite_repository import SqliteWorkItemRepository
from autodev.domain.artifacts import TriageArtifact
from autodev.domain.enums import TaskType, WorkspaceMode
from autodev.domain.enums import WorkflowState as S
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import AutonomyDial, RepoRef, Requirement
from autodev.domain.work_item import WorkItem

NOW = datetime(2026, 7, 15, 10, 30)


def _wi():
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("repo-a"),
        Requirement("fix typo", "repo-a", ("hint",), "raw"),
        AutonomyDial.all_human(),
        NOW,
    )
    wi.type = TaskType.SMALL_CHANGE
    wi.add_artifact("triage", TriageArtifact(TaskType.SMALL_CHANGE, 0.9, WorkspaceMode.REUSE))
    wi.transition_to(S.TRIAGE, "ok", NOW)
    return wi


def test_save_and_get_roundtrip(tmp_path):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    wi = _wi()
    repo.save(wi)
    got = repo.get(wi.id)
    assert got.id == wi.id and got.state is S.TRIAGE and got.type is TaskType.SMALL_CHANGE
    assert got.requirement.goal == "fix typo"
    assert got.artifacts["triage"].workspace_mode is WorkspaceMode.REUSE


def test_claim_runnable_excludes_terminal(tmp_path):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    a = _wi()
    repo.save(a)
    b = _wi()
    b.transition_to(S.FAILED, "x", NOW)
    repo.save(b)
    ids = {wi.id.value for wi in repo.claim_runnable()}
    assert a.id.value in ids and b.id.value not in ids


def test_save_is_upsert(tmp_path):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    wi = _wi()
    repo.save(wi)
    wi.transition_to(S.CONTEXT, "next", NOW)
    repo.save(wi)
    assert repo.get(wi.id).state is S.CONTEXT


def test_full_roundtrip_fidelity(tmp_path):
    from autodev.domain.enums import GatePoint
    from autodev.domain.value_objects import AutonomyDial, Cost

    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("repo-a"),
        Requirement("fix typo", "repo-a", ("hint-x",), "raw text"),
        dial,
        NOW,
    )
    wi.type = TaskType.SMALL_CHANGE
    wi.add_artifact("triage", TriageArtifact(TaskType.SMALL_CHANGE, 0.9, WorkspaceMode.FETCH))
    wi.add_artifact("triage", TriageArtifact(TaskType.SMALL_CHANGE, 0.9, WorkspaceMode.REUSE))
    wi.transition_to(S.TRIAGE, "ok", NOW)
    wi.record_retry("VERIFY:logic")
    wi.add_cost(123)
    repo.save(wi)
    got = repo.get(wi.id)
    assert got.repo_ref == RepoRef("repo-a")
    assert got.requirement.acceptance_hints == ("hint-x",)
    assert got.autonomy_dial == dial
    assert got.retry_ledger.count("VERIFY:logic") == 1
    assert got.cost == Cost(123)
    assert got.created_at == NOW and got.updated_at is not None
    assert got.history and got.history[-1].to_state is S.TRIAGE
    versions = got.versions_of("triage")
    assert len(versions) == 2
    assert versions[0].workspace_mode is WorkspaceMode.FETCH
    assert versions[1].workspace_mode is WorkspaceMode.REUSE
    assert got.artifacts["triage"].workspace_mode is WorkspaceMode.REUSE
