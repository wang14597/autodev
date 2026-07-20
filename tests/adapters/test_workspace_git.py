import subprocess
from pathlib import Path

import pytest

from autodev.adapters.workspace_git import (
    GitWorkspaceAdapter,
    GitWorkspaceConfig,
    _classify,
)
from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError


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
