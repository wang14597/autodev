from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from pathlib import Path

from autodev.domain.artifacts import ContextArtifact
from autodev.domain.value_objects import Requirement, WorkspaceHandle

_JSON = re.compile(r"\{.*\}", re.S)


class ClaudeContextAdapter:
    def __init__(
        self,
        runner: Callable[[str, Path], str],
        autodev_home: Path,
        id_gen: Callable[[], str] = lambda: uuid.uuid4().hex[:8],
    ) -> None:
        self._runner = runner
        self._home = autodev_home
        self._id_gen = id_gen

    def gather(self, requirement: Requirement, handle: WorkspaceHandle) -> ContextArtifact:
        files, summary = self._collect(requirement, handle)
        files, summary = self._review(files, summary, requirement, handle)
        path = self._persist(handle, files, summary, requirement)
        return ContextArtifact(
            workspace_location=handle.location,
            workspace_label=handle.label,
            context_file=str(path),
        )

    def _collect(
        self, requirement: Requirement, handle: WorkspaceHandle
    ) -> tuple[tuple[str, ...], str]:
        prompt = (
            "你在一个代码仓库工作目录里。只读调查与下述需求相关的代码, "
            '输出 JSON: {"relevant_files":[相对路径...],"summary":"对相关代码的理解摘要"}。'
            "不要修改任何文件。\n\n需求: " + requirement.goal
        )
        return self._parse(self._runner(prompt, Path(handle.location)))

    def _review(
        self,
        files: tuple[str, ...],
        summary: str,
        requirement: Requirement,
        handle: WorkspaceHandle,
    ) -> tuple[tuple[str, ...], str]:
        return files, summary  # T4 实现真实复核

    def _parse(self, out: str) -> tuple[tuple[str, ...], str]:
        m = _JSON.search(out)
        if m:
            try:
                data = json.loads(m.group(0))
                files = tuple(str(f) for f in data.get("relevant_files", []))
                return files, str(data.get("summary", ""))
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
        return (), out  # 降级

    def _persist(
        self,
        handle: WorkspaceHandle,
        files: tuple[str, ...],
        summary: str,
        requirement: Requirement,
    ) -> Path:
        work_item_id = Path(handle.location).name
        d = self._home / "workitems" / work_item_id
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"context-{self._id_gen()}.md"
        path.write_text(self._render(files, summary, requirement, handle), encoding="utf-8")
        return path

    def _render(
        self,
        files: tuple[str, ...],
        summary: str,
        requirement: Requirement,
        handle: WorkspaceHandle,
    ) -> str:
        lines = [
            "# 上下文收集结果",
            "",
            f"- 需求: {requirement.goal}",
            f"- 分支: {handle.label}",
            "",
            "## 相关文件",
            "",
        ]
        lines += [f"- `{f}`" for f in files] or ["(无)"]
        lines += ["", "## 摘要", "", summary, ""]
        return "\n".join(lines)
