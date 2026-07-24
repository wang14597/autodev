from datetime import datetime

from autodev.domain.ids import ProjectId
from autodev.domain.project import Project
from autodev.domain.value_objects import AutonomyDial

NOW = datetime(2026, 7, 24, 10, 0, 0)
LATER = datetime(2026, 7, 24, 11, 0, 0)


def test_project_id_new_is_unique():
    a = ProjectId.new()
    b = ProjectId.new()
    assert a != b
    assert a.value != b.value
    assert isinstance(a.value, str) and a.value


def test_create_sets_fields_and_timestamps():
    pid = ProjectId.new()
    p = Project.create(pid, "repo-a", "git@example.com:repo-a.git", "", NOW)
    assert p.id == pid
    assert p.name == "repo-a"
    assert p.repo_source == "git@example.com:repo-a.git"
    assert p.branch == ""
    assert p.autonomy_dial == AutonomyDial.all_human()
    assert p.created_at == NOW
    assert p.updated_at == NOW


def test_create_sets_explicit_branch():
    # 项目跟踪分支创建时显式指定(留空 = 仓库默认分支, 见上一个用例)。
    p = Project.create(ProjectId.new(), "repo-a", "git@example.com:repo-a.git", "develop", NOW)
    assert p.branch == "develop"


def test_mark_prepared_sets_branch_and_bumps_updated_at():
    p = Project.create(ProjectId.new(), "repo-a", "git@example.com:repo-a.git", "", NOW)
    p.mark_prepared("main", LATER)
    assert p.branch == "main"
    assert p.updated_at == LATER
    assert p.created_at == NOW  # created_at 不变
