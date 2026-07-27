from datetime import datetime

import pytest

from autodev.adapters.memory_repository import InMemoryWorkItemRepository
from autodev.adapters.sqlite_repository import SqliteWorkItemRepository
from autodev.domain.artifacts import TriageArtifact
from autodev.domain.enums import TaskType, WorkspaceMode
from autodev.domain.enums import WorkflowState as S
from autodev.domain.ids import ProjectId, WorkItemId
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


def test_list_all_includes_terminal(tmp_path):
    # 与 claim_runnable 不同：list_all 返回所有工作项(含终态), 供控制台列表持久展示。
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    a = _wi()
    repo.save(a)
    b = _wi()
    b.transition_to(S.FAILED, "x", NOW)
    repo.save(b)
    ids = {wi.id.value for wi in repo.list_all()}
    assert ids == {a.id.value, b.id.value}


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


def test_project_id_roundtrips_when_set(tmp_path):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    pid = ProjectId.new()
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("repo-a"),
        Requirement("fix typo", "repo-a", (), "raw"),
        AutonomyDial.all_human(),
        NOW,
        project_id=pid,
    )
    repo.save(wi)
    got = repo.get(wi.id)
    assert got.project_id == pid


def test_project_id_defaults_to_none_when_absent():
    # 未归类工作项(project_id=None)往返序列化仍为 None; 兼容旧数据(无 project_id 键)。
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("repo-a"),
        Requirement("fix typo", "repo-a", (), "raw"),
        AutonomyDial.all_human(),
        NOW,
    )
    assert wi.project_id is None

    from autodev.adapters.sqlite_repository import _from_dict, _to_dict

    d = _to_dict(wi)
    assert d["project_id"] is None
    del d["project_id"]  # 模拟旧数据缺失该键
    got = _from_dict(d)
    assert got.project_id is None


def test_base_branch_roundtrips_when_set(tmp_path):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("repo-a"),
        Requirement("fix typo", "repo-a", (), "raw"),
        AutonomyDial.all_human(),
        NOW,
        base_branch="develop",
    )
    repo.save(wi)
    got = repo.get(wi.id)
    assert got.base_branch == "develop"


def test_base_branch_defaults_to_none_when_absent():
    # 未指定 base_branch 的旧数据(缺该键)往返仍为 None。
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("repo-a"),
        Requirement("fix typo", "repo-a", (), "raw"),
        AutonomyDial.all_human(),
        NOW,
    )
    assert wi.base_branch is None

    from autodev.adapters.sqlite_repository import _from_dict, _to_dict

    d = _to_dict(wi)
    assert d["base_branch"] is None
    del d["base_branch"]  # 模拟旧数据缺失该键
    got = _from_dict(d)
    assert got.base_branch is None


def _sqlite_repo(tmp_path):
    return SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))


def _memory_repo(tmp_path):
    return InMemoryWorkItemRepository()


@pytest.mark.parametrize("factory", [_sqlite_repo, _memory_repo])
def test_delete_removes_work_item(tmp_path, factory):
    repo = factory(tmp_path)
    wi = _wi()
    repo.save(wi)

    repo.delete(wi.id)

    with pytest.raises(KeyError):
        repo.get(wi.id)


# --- 切片 2.1：TriageArtifact 风险维度序列化 ---


def test_triage_risk_and_signals_roundtrip(tmp_path):
    from autodev.domain.enums import RiskLevel

    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("repo-a"),
        Requirement("delete old tokens", "repo-a", (), "delete old tokens"),
        AutonomyDial.all_human(),
        NOW,
    )
    wi.type = TaskType.SMALL_CHANGE
    wi.add_artifact(
        "triage",
        TriageArtifact(
            TaskType.SMALL_CHANGE, 0.7, WorkspaceMode.REUSE, RiskLevel.HIGH, ("keyword:delete",)
        ),
    )
    wi.transition_to(S.TRIAGE, "ok", NOW)
    repo.save(wi)

    got = repo.get(wi.id).artifacts["triage"]
    assert got.risk is RiskLevel.HIGH
    assert got.signals == ("keyword:delete",)


def test_legacy_triage_dict_without_risk_defaults_low():
    from autodev.adapters.sqlite_repository import _artifact_from_dict
    from autodev.domain.enums import RiskLevel

    legacy = {
        "__t": "TriageArtifact",
        "level": "SMALL_CHANGE",
        "confidence": 0.9,
        "workspace_mode": "REUSE",
    }
    art = _artifact_from_dict(legacy)
    assert art.risk is RiskLevel.LOW
    assert art.signals == ()


# --- LLM 分诊子迭代 A：autonomy_enabled + intent 序列化 ---


def test_autonomy_enabled_roundtrips(tmp_path):
    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("r"),
        Requirement("g", "r", (), "g"),
        AutonomyDial.all_human(),
        NOW,
        autonomy_enabled=True,
    )
    repo.save(wi)
    assert repo.get(wi.id).autonomy_enabled is True


def test_triage_intent_roundtrips(tmp_path):
    from autodev.domain.enums import RiskLevel, TriageIntent

    repo = SqliteWorkItemRepository(str(tmp_path / "db.sqlite"))
    wi = WorkItem.create(
        WorkItemId.new(),
        RepoRef("r"),
        Requirement("g", "r", (), "g"),
        AutonomyDial.all_human(),
        NOW,
    )
    wi.add_artifact(
        "triage",
        TriageArtifact(
            TaskType.SMALL_CHANGE,
            0.9,
            WorkspaceMode.REUSE,
            RiskLevel.LOW,
            (),
            TriageIntent.CONSULTATION,
        ),
    )
    wi.transition_to(S.TRIAGE, "ok", NOW)
    repo.save(wi)
    assert repo.get(wi.id).artifacts["triage"].intent is TriageIntent.CONSULTATION


def test_legacy_triage_dict_defaults_intent_actionable():
    from autodev.adapters.sqlite_repository import _artifact_from_dict
    from autodev.domain.enums import TriageIntent

    art = _artifact_from_dict(
        {
            "__t": "TriageArtifact",
            "level": "SMALL_CHANGE",
            "confidence": 0.9,
            "workspace_mode": "REUSE",
        }
    )
    assert art.intent is TriageIntent.ACTIONABLE
