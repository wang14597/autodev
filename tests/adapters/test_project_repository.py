from datetime import datetime

import pytest

from autodev.adapters.project_repository import InMemoryProjectRepository, SqliteProjectRepository
from autodev.domain.enums import GatePoint, TaskType
from autodev.domain.ids import ProjectId
from autodev.domain.project import Project
from autodev.domain.value_objects import AutonomyDial

NOW = datetime(2026, 7, 24, 10, 0, 0)
LATER = datetime(2026, 7, 24, 11, 0, 0)


def _sqlite_repo(tmp_path):
    return SqliteProjectRepository(str(tmp_path / "projects.sqlite3"))


def _memory_repo(tmp_path):
    return InMemoryProjectRepository()


REPO_FACTORIES = [_sqlite_repo, _memory_repo]


@pytest.mark.parametrize("factory", REPO_FACTORIES)
def test_save_and_get_roundtrip_all_fields(tmp_path, factory):
    repo = factory(tmp_path)
    dial = AutonomyDial(frozenset({(TaskType.SMALL_CHANGE, "repo-a", GatePoint.REVIEW_GATE)}))
    p = Project.create(ProjectId.new(), "repo-a", "git@example.com:repo-a.git", "", NOW)
    p.autonomy_dial = dial
    p.mark_prepared("main", LATER)
    repo.save(p)

    got = repo.get(p.id)
    assert got.id == p.id
    assert got.name == "repo-a"
    assert got.repo_source == "git@example.com:repo-a.git"
    assert got.branch == "main"
    assert got.autonomy_dial == dial
    assert got.created_at == NOW
    assert got.updated_at == LATER


@pytest.mark.parametrize("factory", REPO_FACTORIES)
def test_get_missing_raises_key_error(tmp_path, factory):
    repo = factory(tmp_path)
    with pytest.raises(KeyError):
        repo.get(ProjectId.new())


@pytest.mark.parametrize("factory", REPO_FACTORIES)
def test_get_by_name_hit_and_miss(tmp_path, factory):
    repo = factory(tmp_path)
    p = Project.create(ProjectId.new(), "repo-a", "src-a", "", NOW)
    repo.save(p)

    found = repo.get_by_name("repo-a")
    assert found is not None
    assert found.id == p.id

    assert repo.get_by_name("does-not-exist") is None


@pytest.mark.parametrize("factory", REPO_FACTORIES)
def test_list_all(tmp_path, factory):
    repo = factory(tmp_path)
    a = Project.create(ProjectId.new(), "repo-a", "src-a", "", NOW)
    b = Project.create(ProjectId.new(), "repo-b", "src-b", "", NOW)
    repo.save(a)
    repo.save(b)

    names = {p.name for p in repo.list_all()}
    assert names == {"repo-a", "repo-b"}


@pytest.mark.parametrize("factory", REPO_FACTORIES)
def test_delete_removes_project(tmp_path, factory):
    repo = factory(tmp_path)
    p = Project.create(ProjectId.new(), "repo-a", "src-a", "", NOW)
    repo.save(p)

    repo.delete(p.id)

    with pytest.raises(KeyError):
        repo.get(p.id)
    assert repo.list_all() == []


@pytest.mark.parametrize("factory", REPO_FACTORIES)
def test_save_is_upsert(tmp_path, factory):
    repo = factory(tmp_path)
    p = Project.create(ProjectId.new(), "repo-a", "src-a", "", NOW)
    repo.save(p)
    p.mark_prepared("develop", LATER)
    repo.save(p)

    got = repo.get(p.id)
    assert got.branch == "develop"
    assert got.updated_at == LATER
