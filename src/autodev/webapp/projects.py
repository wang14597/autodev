# src/autodev/webapp/projects.py
"""项目登记表：把"项目"输入解析成 repo_map 里的项目名。

支持两种输入：
- 已登记的项目名 → 原样返回。
- 本地 git 仓库的目录路径 → 自动以目录名登记进 repo_map(值为该裸本地路径),
  并持久化到磁盘(重启仍在)。F1 见裸本地路径会直接在其上开 worktree(共享对象库,
  不整仓克隆)。这样用户直接填项目目录即可, 无需预先配 AUTODEV_REPO_MAP。

repo_map 是与 GitWorkspaceConfig 共享的同一个 dict, 运行时新增映射对 F1 立即生效。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from autodev.adapters.workspace_git import WORKTREE_SCHEME


def _default_is_git_repo(path: Path) -> bool:
    # 普通工作副本/子模块/worktree 都有 .git(目录或文件)。
    return (path / ".git").exists()


class ProjectRegistry:
    def __init__(
        self,
        repo_map: dict[str, str],
        persist_path: Path | None = None,
        is_git_repo: Callable[[Path], bool] = _default_is_git_repo,
    ) -> None:
        self._repo_map = repo_map
        self._persist_path = persist_path
        self._is_git_repo = is_git_repo

    @property
    def repo_map(self) -> dict[str, str]:
        """与 GitWorkspaceConfig 共享的同一个 dict。"""
        return self._repo_map

    def names(self) -> list[str]:
        return sorted(self._repo_map)

    def resolve(self, raw: str) -> str:
        """把"项目"输入解析成 repo_map 里的项目名(必要时自动登记本地 git 仓库)。"""
        raw = raw.strip()
        if raw in self._repo_map:
            return raw
        path = Path(raw).expanduser()
        if path.is_dir() and self._is_git_repo(path):
            name = path.resolve().name
            self._repo_map[name] = self._resolve_repo_source(raw)
            self._persist()
            return name
        return raw  # 既非已登记名, 也不是本地 git 仓库 → 原样交给下游(CREATE/或报错)

    def register(self, name: str, repo_input: str) -> str:
        """显式两步登记：调用方给定项目名, 仅解析 `repo_input` 得 repo_source。

        与 `resolve()` 共享"输入 → repo_source"解析逻辑(`_resolve_repo_source`)；
        区别在于 `resolve()` 从本地目录名派生项目名, 而 `register()` 的项目名由
        调用方(两步创建流程里的 create_project)显式提供。
        """
        repo_source = self._resolve_repo_source(repo_input)
        self._repo_map[name] = repo_source
        self._persist()
        return repo_source

    def unregister(self, name: str) -> None:
        self._repo_map.pop(name, None)
        self._persist()

    def _resolve_repo_source(self, repo_input: str) -> str:
        """把任意仓库输入解析为 repo_map 值语义的 repo_source。

        本地 git 目录 → `worktree:<resolved path>`(共享对象库开 worktree,
        不整仓克隆)；否则原样返回(远程 URL 或已是 repo_source 形式的字符串)。
        """
        raw = repo_input.strip()
        path = Path(raw).expanduser()
        if path.is_dir() and self._is_git_repo(path):
            return f"{WORKTREE_SCHEME}{path.resolve()}"
        return raw

    def _persist(self) -> None:
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._persist_path.write_text(
            json.dumps(self._repo_map, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def load_registry(
    env_repo_map: dict[str, str],
    persist_path: Path,
    is_git_repo: Callable[[Path], bool] = _default_is_git_repo,
) -> ProjectRegistry:
    """合并环境变量映射与磁盘持久化映射(环境变量优先), 构造登记表。"""
    merged = dict(env_repo_map)
    if persist_path.is_file():
        try:
            data = json.loads(persist_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(key, str) and isinstance(value, str):
                    merged.setdefault(key, value)  # 环境变量优先
    return ProjectRegistry(merged, persist_path, is_git_repo)
