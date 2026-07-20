import subprocess
from pathlib import Path

import pytest

from autodev.adapters.workspace_git import (
    GitWorkspaceAdapter,
    GitWorkspaceConfig,
    _classify,
)
from autodev.domain.enums import FailureKind, WorkspaceMode
from autodev.domain.errors import StageError
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import RepoRef


def _cfg(tmp_path: Path, repo_map=None) -> GitWorkspaceConfig:
    return GitWorkspaceConfig(
        repo_map=repo_map or {},
        mirror_dir=tmp_path / "mirrors",
        workspaces_dir=tmp_path / "ws",
    )


def test_classify_maps_stderr_to_failure_kind():
    assert _classify("fatal: Could not resolve host: gitlab") is FailureKind.TRANSIENT
    assert _classify("git@x: Permission denied (publickey).") is FailureKind.FATAL
    assert _classify("error: pathspec 'x' did not match") is FailureKind.LOGIC


def test_git_nonzero_raises_stageerror_classified(tmp_path):
    def fake_run(*a, **k):
        return subprocess.CompletedProcess(a, 1, stdout="", stderr="Could not resolve host: gitlab")

    adapter = GitWorkspaceAdapter(_cfg(tmp_path), run=fake_run)
    with pytest.raises(StageError) as ei:
        adapter._git(["ls-remote", "x"])
    assert ei.value.failure_kind is FailureKind.TRANSIENT


def test_git_missing_binary_is_fatal(tmp_path):
    def fake_run(*a, **k):
        raise FileNotFoundError("git")

    adapter = GitWorkspaceAdapter(_cfg(tmp_path), run=fake_run)
    with pytest.raises(StageError) as ei:
        adapter._git(["status"])
    assert ei.value.failure_kind is FailureKind.FATAL


def test_git_timeout_is_transient(tmp_path):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    adapter = GitWorkspaceAdapter(_cfg(tmp_path), run=fake_run)
    with pytest.raises(StageError) as ei:
        adapter._git(["clone", "x"])
    assert ei.value.failure_kind is FailureKind.TRANSIENT


def _make_remote(path: Path) -> str:
    """建一个带一个提交的本地 git 仓, 返回其路径(可作 file:// 远程)。"""
    path.mkdir(parents=True)

    def g(*args: str) -> None:
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)

    g("init", "--initial-branch=main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (path / "app.py").write_text("x = 1\n")
    g("add", ".")
    g("commit", "-m", "init")
    return str(path)


def test_repo_status_unmapped_is_all_false(tmp_path):
    a = GitWorkspaceAdapter(_cfg(tmp_path))
    st = a.repo_status(RepoRef("nope"))
    assert st.exists_local is False and st.exists_remote is False


def test_repo_status_mapped_remote_true(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    st = a.repo_status(RepoRef("r"))
    assert st.exists_remote is True and st.exists_local is False


def test_repo_status_local_true_when_mirror_present(tmp_path):
    cfg = _cfg(tmp_path, repo_map={})
    (cfg.mirror_dir / "r.git").mkdir(parents=True)
    a = GitWorkspaceAdapter(cfg)
    assert a.repo_status(RepoRef("r")).exists_local is True


def _mirror_from_remote(adapter, name, remote_url):
    # 借 FETCH 建 mirror
    adapter._git(["clone", "--mirror", remote_url, str(adapter._mirror_path(name))])


def test_provision_fetch_creates_worktree_on_branch(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    h = a.provision(WorkItemId("wi123456"), RepoRef("r"), WorkspaceMode.FETCH, "autodev/wi123456")
    ws = Path(h.location)
    assert ws.exists() and (ws / "app.py").read_text() == "x = 1\n"
    assert h.label == "autodev/wi123456"
    # 分支正确
    cur = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ws, capture_output=True, text=True
    ).stdout.strip()
    assert cur == "autodev/wi123456"
    assert a._mirror_path("r").exists()  # mirror 落地


def test_provision_reuse_requires_existing_mirror(tmp_path):
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={}))
    with pytest.raises(StageError) as ei:
        a.provision(WorkItemId("w"), RepoRef("r"), WorkspaceMode.REUSE, "b")
    assert ei.value.failure_kind is FailureKind.FATAL


def test_provision_reuse_uses_cached_mirror(tmp_path):
    remote = _make_remote(tmp_path / "remote")
    a = GitWorkspaceAdapter(_cfg(tmp_path, repo_map={"r": remote}))
    _mirror_from_remote(a, "r", remote)  # 预置 mirror
    h = a.provision(WorkItemId("w2"), RepoRef("r"), WorkspaceMode.REUSE, "autodev/w2")
    assert Path(h.location, "app.py").exists()
