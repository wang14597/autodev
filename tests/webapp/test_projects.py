# tests/webapp/test_projects.py
from __future__ import annotations

import json
from pathlib import Path

from autodev.webapp.projects import ProjectRegistry, load_registry


def _git_dir(tmp_path: Path, name: str) -> Path:
    d = tmp_path / name
    (d / ".git").mkdir(parents=True)
    return d


def test_resolve_returns_known_name_unchanged(tmp_path: Path) -> None:
    reg = ProjectRegistry({"svc": "git@host:team/svc.git"}, tmp_path / "repos.json")
    assert reg.resolve("svc") == "svc"


def test_resolve_local_git_dir_registers_file_url(tmp_path: Path) -> None:
    repo_dir = _git_dir(tmp_path, "voice-agent")
    repo_map: dict[str, str] = {}
    reg = ProjectRegistry(repo_map, tmp_path / "repos.json")

    name = reg.resolve(str(repo_dir))

    assert name == "voice-agent"
    assert repo_map["voice-agent"] == f"worktree:{repo_dir.resolve()}"
    # 同一个 dict 被改写(GitWorkspaceConfig 共享它 → F1 立即可见)
    assert "voice-agent" in reg.repo_map


def test_resolve_persists_to_disk(tmp_path: Path) -> None:
    repo_dir = _git_dir(tmp_path, "voice-agent")
    persist = tmp_path / "repos.json"
    reg = ProjectRegistry({}, persist)

    reg.resolve(str(repo_dir))

    saved = json.loads(persist.read_text(encoding="utf-8"))
    assert saved["voice-agent"] == f"worktree:{repo_dir.resolve()}"


def test_resolve_non_git_path_returned_unchanged(tmp_path: Path) -> None:
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    reg = ProjectRegistry({}, tmp_path / "repos.json")
    assert reg.resolve(str(plain)) == str(plain)
    assert reg.repo_map == {}


def test_resolve_unknown_string_returned_unchanged(tmp_path: Path) -> None:
    reg = ProjectRegistry({}, tmp_path / "repos.json")
    assert reg.resolve("some-remote-name") == "some-remote-name"
    assert reg.repo_map == {}


def test_names_sorted(tmp_path: Path) -> None:
    reg = ProjectRegistry({"b": "u", "a": "u"}, tmp_path / "repos.json")
    assert reg.names() == ["a", "b"]


def test_load_registry_merges_env_and_disk_env_wins(tmp_path: Path) -> None:
    persist = tmp_path / "repos.json"
    persist.write_text(json.dumps({"a": "disk-url", "c": "disk-c"}), encoding="utf-8")
    reg = load_registry({"a": "env-url", "b": "env-b"}, persist)
    assert reg.repo_map == {"a": "env-url", "b": "env-b", "c": "disk-c"}


def test_load_registry_tolerates_missing_or_bad_file(tmp_path: Path) -> None:
    reg = load_registry({"a": "u"}, tmp_path / "nope.json")
    assert reg.repo_map == {"a": "u"}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    reg2 = load_registry({"a": "u"}, bad)
    assert reg2.repo_map == {"a": "u"}
