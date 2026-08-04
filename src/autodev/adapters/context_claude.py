from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from autodev.domain.artifacts import ContextArtifact
from autodev.domain.errors import StageError
from autodev.domain.value_objects import Requirement, WorkspaceHandle

_MIN_REVIEW_LEN = 20


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
        doc = self._collect(requirement, handle)
        doc = self._review(doc, requirement, handle)
        path = self._persist(handle, requirement, doc)
        return ContextArtifact(
            workspace_location=handle.location,
            workspace_label=handle.label,
            context_file=str(path),
        )

    def _collect(self, requirement: Requirement, handle: WorkspaceHandle) -> str:
        prompt = (
            "你在一个代码仓库工作目录里。只读调查与下述需求相关的代码, "
            "产出一份 Markdown 格式的上下文文档, 包含以下小节: "
            "`## 相关文件`(逐个列出相关文件, 每个附一行简短的相关性说明), "
            "`## 现状理解`(对现有相关代码的理解), "
            "`## 改动要点`(为实现该需求大致需要改动/关注的地方)。"
            "只输出 Markdown 文档本身, 不要额外解释; 不要修改任何文件。\n\n"
            "需求: " + requirement.goal
        )
        return self._runner(prompt, Path(handle.location)).strip()

    def _review(self, doc: str, requirement: Requirement, handle: WorkspaceHandle) -> str:
        prompt = (
            "下面是对本仓库的第一遍上下文收集结果(Markdown 文档)。请对照真实代码核对其"
            "相关性/完整性/准确性, 补充遗漏、去除无关内容、修正不准确之处, "
            "只输出改进后的完整 Markdown 文档本身, 不要有任何前后说明文字。"
            "只读, 不要修改任何文件。\n\n"
            f"需求: {requirement.goal}\n\n第一遍文档:\n{doc}"
        )
        try:
            improved = self._runner(prompt, Path(handle.location)).strip()
        except StageError:
            return doc  # 复核这一遍调用失败 → 降级回第一遍(第一遍的结果仍然可用)
        if len(improved) < _MIN_REVIEW_LEN:
            # 复核调用成功了, 但产出空/过短/退化内容, 比第一遍结果更差 → 降级保留第一遍
            return doc
        return improved

    def _persist(self, handle: WorkspaceHandle, requirement: Requirement, doc: str) -> Path:
        work_item_id = Path(handle.location).name
        d = self._home / "workitems" / work_item_id
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"context-{self._id_gen()}.md"
        header = (
            f"# 上下文收集结果\n\n- 需求: {requirement.goal}\n- 分支: {handle.label}\n\n---\n\n"
        )
        path.write_text(header + doc, encoding="utf-8")
        return path
