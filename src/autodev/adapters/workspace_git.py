from __future__ import annotations

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


# repo_map 值的显式标记: 表示"直接在该本地仓库上开 worktree", 而非镜像克隆。
WORKTREE_SCHEME = "worktree:"


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

    def _local_source(self, name: str) -> Path | None:
        """若 name 用 `worktree:` 前缀显式登记为本地仓库, 返回其路径; 否则 None。

        `worktree:<path>` 是控制台自动登记本地项目时用的显式意图标记, 表示"直接在该
        本地仓库上开 linked worktree(共享对象库, 不整仓克隆)"。其它一切值(含普通本地
        路径、file://、ssh://、https://)一律走镜像克隆路径, 语义不变。
        """
        url = self._config.repo_map.get(name)
        if not url or not url.startswith(WORKTREE_SCHEME):
            return None
        path = Path(url[len(WORKTREE_SCHEME) :]).expanduser()
        return path if (path / ".git").exists() else None

    def _local_base(self, src: Path) -> str:
        try:
            return self._git(["-C", str(src), "symbolic-ref", "--short", "HEAD"])
        except StageError:
            return self._git(["-C", str(src), "rev-parse", "HEAD"])

    def _rev_parse_ok(self, cwd: Path, ref: str) -> bool:
        """`git rev-parse --verify --quiet <ref>` 是否成功(引用是否存在), 不抛异常。"""
        try:
            self._git(["rev-parse", "--verify", "--quiet", ref], cwd=cwd)
            return True
        except StageError:
            return False

    def repo_status(self, repo: RepoRef) -> RepoStatus:
        if self._local_source(repo.name) is not None or self._mirror_path(repo.name).exists():
            # worktree: 本地仓库确实存在, 或该仓库的 mirror 已建好(已 prepare 过)
            # → 视为本地可用(triage 据此选 REUSE), 不再发起 ls-remote 探测。
            return RepoStatus(exists_local=True, exists_remote=False)
        exists_remote = False
        url = self._config.repo_map.get(repo.name)
        if url:
            try:
                self._git(["ls-remote", url])
                exists_remote = True
            except StageError:
                exists_remote = False
        return RepoStatus(exists_local=False, exists_remote=exists_remote)

    def prepare(self, repo: RepoRef, branch: str | None = None) -> str:
        """同项目共享的一次性 setup(也是"刷新"用的重入口): 建/刷新 mirror(或对本地仓库
        best-effort fetch 其 origin), 解析并返回跟踪分支。

        幂等: 本地仓库每次重新 fetch(best-effort, 无 origin/离线不报错)+ 重读 HEAD(或直接
        用给定 branch); 远程仓库通过 FETCH 模式复用已存在的 mirror(`_ensure_mirror` 对
        已存在的 mirror 走 fetch --prune, 不会重新整仓克隆)。
        """
        src = self._local_source(repo.name)
        if src is not None:
            try:
                # best-effort: 本地仓库可能没有 origin(纯本地项目)或离线, 都不应阻断 prepare。
                self._git(["-C", str(src), "fetch", "--all", "--prune"])
            except StageError:
                pass
            return branch if branch else self._local_base(src)
        mirror = self._mirror_path(repo.name)
        self._ensure_mirror(mirror, repo.name, WorkspaceMode.FETCH)
        if branch:
            return branch
        # _base_ref 对已建 remote-tracking 的 mirror 返回 "origin/<branch>"(供 provision
        # 直接当 worktree 起点用); prepare 对外承诺的是"跟踪分支名"本身, 去掉前缀。
        return self._base_ref(mirror).removeprefix("origin/")

    def list_branches(self, repo: RepoRef) -> list[str]:
        """列出该仓库当前已知的 origin/* 分支(不含 "origin/" 前缀, 不含 HEAD)。

        worktree: 本地仓库用其 `.git` 所在目录; 否则用已建好的 mirror。两者皆无
        (未 prepare 过/仓库未登记)时视为"尚不可列", 返回空列表而非报错。
        """
        src = self._local_source(repo.name)
        if src is not None:
            git_dir = src
        else:
            mirror = self._mirror_path(repo.name)
            if not mirror.exists():
                return []
            git_dir = mirror
        try:
            out = self._git(
                ["-C", str(git_dir), "for-each-ref", "--format=%(refname)", "refs/remotes/origin"]
            )
        except StageError:
            return []
        # 用完整 refname 而非 refname:short: origin/HEAD 的短名会被 git 折叠成
        # "origin"(丢了 "/HEAD"), 没法靠字符串排除; 完整名去掉固定前缀更可靠。
        prefix = "refs/remotes/origin/"
        names: set[str] = set()
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith(prefix):
                continue
            name = line[len(prefix) :]
            if name == "HEAD":
                continue
            names.add(name)
        return sorted(names)

    def provision(
        self,
        work_item_id: WorkItemId,
        repo: RepoRef,
        mode: WorkspaceMode,
        branch: str,
        base_branch: str | None = None,
    ) -> WorkspaceHandle:
        mirror = self._mirror_path(repo.name)
        ws = self._config.workspaces_dir / work_item_id.value
        if ws.exists():  # 幂等: 已有 worktree
            current = self._git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=ws)
            if current == branch:
                return WorkspaceHandle(location=str(ws), label=branch)
            # 分支不符: 走与公共 cleanup 相同的移除路径, 再让 provision 正常路径重建。
            self.cleanup(WorkspaceHandle(location=str(ws), label=current))

        src = self._local_source(repo.name)
        if src is not None:
            # 本地 git 仓库: 直接在其上开 linked worktree(共享对象库, 不整仓克隆)。
            # worktree 落在 workspaces_dir/<id>, 仅在源仓 .git 里留可删的分支+worktree 注册,
            # 不碰源仓工作目录。cleanup 通过 --git-common-dir 自动定位到源仓, 无需特判。
            self._config.workspaces_dir.mkdir(parents=True, exist_ok=True)
            # 本地仓无 origin/<base_branch>(纯本地项目, 或该分支未推送过)时退回本地同名分支。
            base = (
                self._resolve_base(src, base_branch, fallback=base_branch)
                if base_branch
                else self._local_base(src)
            )
            self._git(["-C", str(src), "worktree", "add", "-b", branch, str(ws), base])
            return WorkspaceHandle(location=str(ws), label=branch)

        self._ensure_mirror(mirror, repo.name, mode)
        # 镜像必来自 origin; 若 base_branch 无对应 remote-tracking 分支, 退回镜像默认分支
        # (而非把 base_branch 当本地分支名, 镜像里本无本地分支)。
        base = (
            self._resolve_base(mirror, base_branch, fallback=self._base_ref(mirror))
            if base_branch
            else self._base_ref(mirror)
        )
        self._config.workspaces_dir.mkdir(parents=True, exist_ok=True)
        self._git(["-C", str(mirror), "worktree", "add", "-b", branch, str(ws), base])
        return WorkspaceHandle(location=str(ws), label=branch)

    def _resolve_base(self, cwd: Path, base_branch: str, fallback: str) -> str:
        """worktree 基点: base_branch 有对应 remote-tracking 分支(fetch 后最新)则用之;
        否则退回调用方给定的 fallback。"""
        origin_ref = f"origin/{base_branch}"
        if self._rev_parse_ok(cwd, origin_ref):
            return origin_ref
        return fallback

    def cleanup(self, handle: WorkspaceHandle) -> None:
        loc = Path(handle.location)
        if not loc.exists():  # 幂等: 已经不存在, no-op
            return
        common = self._git(["-C", str(loc), "rev-parse", "--git-common-dir"])
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = (loc / common_path).resolve()
        self._git(["-C", str(common_path), "worktree", "remove", "--force", str(loc)])
        try:
            self._git(["-C", str(common_path), "branch", "-D", handle.label])
        except StageError:
            pass  # 分支已不存在(例如从未成功创建), 忽略
        self._git(["-C", str(common_path), "worktree", "prune"])

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
