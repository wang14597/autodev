from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from autodev.domain.enums import FailureKind, WorkspaceMode
from autodev.domain.errors import StageError
from autodev.domain.ids import WorkItemId
from autodev.domain.value_objects import RepoRef, RepoStatus, WorkspaceHandle

_NETWORK_HINTS = (
    "could not resolve host",
    "connection",
    "timed out",
    "unable to access",
    "network is unreachable",
    "failed to connect",
)
_AUTH_HINTS = (
    "authentication failed",
    "permission denied",
    "access denied",
    "could not read from remote",
    "publickey",
)


def _classify(stderr: str) -> FailureKind:
    s = stderr.lower()
    if any(h in s for h in _NETWORK_HINTS):
        return FailureKind.TRANSIENT
    if any(h in s for h in _AUTH_HINTS):
        return FailureKind.FATAL
    return FailureKind.LOGIC


@dataclass(frozen=True)
class GitWorkspaceConfig:
    repo_map: dict[str, str]
    mirror_dir: Path
    workspaces_dir: Path


class GitWorkspaceAdapter:
    def __init__(
        self,
        config: GitWorkspaceConfig,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout: int = 60,
    ) -> None:
        self._config = config
        self._run = run
        self._timeout = timeout

    def _git(self, args: list[str], cwd: Path | None = None) -> str:
        try:
            proc = self._run(
                ["git", *args],
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise StageError(FailureKind.TRANSIENT, f"git 超时: {' '.join(args)}") from e
        except FileNotFoundError as e:
            raise StageError(FailureKind.FATAL, "git 不可用") from e
        if proc.returncode != 0:
            raise StageError(
                _classify(proc.stderr),
                f"git {' '.join(args)} 失败: {proc.stderr.strip()[:200]}",
            )
        return proc.stdout.strip()

    def _mirror_path(self, name: str) -> Path:
        return self._config.mirror_dir / f"{name}.git"

    def _resolve_url(self, name: str) -> str:
        url = self._config.repo_map.get(name)
        if not url:
            raise StageError(FailureKind.FATAL, f"仓库未在 repo_map 登记: {name}")
        return url

    def repo_status(self, repo: RepoRef) -> RepoStatus:
        exists_local = self._mirror_path(repo.name).exists()
        exists_remote = False
        url = self._config.repo_map.get(repo.name)
        if url:
            try:
                self._git(["ls-remote", url])
                exists_remote = True
            except StageError:
                exists_remote = False
        return RepoStatus(exists_local=exists_local, exists_remote=exists_remote)

    def provision(
        self, work_item_id: WorkItemId, repo: RepoRef, mode: WorkspaceMode, branch: str
    ) -> WorkspaceHandle:
        mirror = self._mirror_path(repo.name)
        ws = self._config.workspaces_dir / work_item_id.value
        if ws.exists():  # 幂等: 已有 worktree
            current = self._git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=ws)
            if current == branch:
                return WorkspaceHandle(location=str(ws), label=branch)
            self._discard_worktree(mirror, ws)
        self._ensure_mirror(mirror, repo.name, mode)
        base = self._base_ref(mirror)
        self._config.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self._git(["-C", str(mirror), "worktree", "add", "-b", branch, str(ws), base])
        return WorkspaceHandle(location=str(ws), label=branch)

    def _discard_worktree(self, mirror: Path, ws: Path) -> None:
        # 分支不符: 移除旧 worktree 及其本地分支, 让 provision 走正常路径重建
        # (F1-T5 将扩展为与公共 cleanup 统一的完整实现)。
        if mirror.exists():
            current = self._git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=ws)
            self._git(["-C", str(mirror), "worktree", "remove", "--force", str(ws)])
            try:
                self._git(["-C", str(mirror), "branch", "-D", current])
            except StageError:
                pass  # 分支已不存在(例如从未成功创建), 忽略
        else:
            shutil.rmtree(ws, ignore_errors=True)

    def _ensure_mirror(self, mirror: Path, name: str, mode: WorkspaceMode) -> None:
        if mode is WorkspaceMode.REUSE:
            if not mirror.exists():
                raise StageError(FailureKind.FATAL, f"REUSE 模式但本地无 mirror: {name}")
            return
        if mode is WorkspaceMode.FETCH:
            if mirror.exists():
                # 标准 remote-tracking refspec: 仅裁剪 refs/remotes/origin/*,
                # 不会碰到本地创建的 refs/heads/autodev/* 特性分支(其它工作项的 worktree 所在)。
                self._git(["-C", str(mirror), "fetch", "--prune", "origin"])
            else:
                url = self._resolve_url(name)
                mirror.parent.mkdir(parents=True, exist_ok=True)
                self._git(["init", "--bare", str(mirror)])
                self._git(["-C", str(mirror), "remote", "add", "origin", url])
                self._git(["-C", str(mirror), "fetch", "--prune", "origin"])
                self._git(["-C", str(mirror), "remote", "set-head", "origin", "-a"])
            return
        self._create_seed_mirror(mirror)  # CREATE (Task 4)

    def _base_ref(self, mirror: Path) -> str:
        # 优先用 remote-tracking HEAD(FETCH/REUSE); CREATE 的种子 mirror 无 origin,
        # 退回本地 HEAD。
        try:
            return self._git(
                ["-C", str(mirror), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"]
            )
        except StageError:
            return self._git(["-C", str(mirror), "symbolic-ref", "--short", "HEAD"])

    def _create_seed_mirror(self, mirror: Path) -> None:
        mirror.parent.mkdir(parents=True, exist_ok=True)
        self._git(["init", "--bare", "--initial-branch=main", str(mirror)])
        with tempfile.TemporaryDirectory() as tmp:
            self._git(["init", "--initial-branch=main", tmp])
            self._git(
                [
                    "-C",
                    tmp,
                    "-c",
                    "user.name=AutoDev",
                    "-c",
                    "user.email=autodev@local",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "chore: init",
                ]
            )
            self._git(["-C", tmp, "push", str(mirror), "main"])
