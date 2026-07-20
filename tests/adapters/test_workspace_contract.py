import subprocess
from pathlib import Path

import pytest

from autodev.adapters.workspace_git import GitWorkspaceAdapter, GitWorkspaceConfig
from autodev.domain.enums import WorkspaceMode
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import RepoRef
from tests.fakes import FakeWorkspace


def _make_remote(path: Path) -> str:
    path.mkdir(parents=True)

    def g(*a):
        subprocess.run(["git", *a], cwd=path, check=True, capture_output=True)

    g("init", "--initial-branch=main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (path / "app.py").write_text("x = 1\n")
    g("add", ".")
    g("commit", "-m", "init")
    return str(path)


def _real(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    return GitWorkspaceAdapter(
        GitWorkspaceConfig(
            repo_map={"r": remote}, mirror_dir=tmp_path / "m", workspaces_dir=tmp_path / "w"
        )
    )


@pytest.fixture(params=["fake", "real"])
def workspace(request, tmp_path):
    return FakeWorkspace(local=True) if request.param == "fake" else _real(tmp_path)


def test_provision_returns_handle_with_requested_label(workspace):
    h = workspace.provision(WorkItemId("k1"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/k1")
    assert h.label == "autodev/k1"
    assert h.location  # 非空路径


def test_cleanup_accepts_provisioned_handle(workspace):
    h = workspace.provision(WorkItemId("k2"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/k2")
    workspace.cleanup(h)  # 两种实现都不应抛
