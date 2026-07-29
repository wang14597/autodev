from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from autodev.domain.artifacts import ContextArtifact, DesignArtifact
from autodev.domain.value_objects import Requirement


class ClaudeDesignAdapter:
    """DesignPort 真实实现：worktree 内只读跑 claude，单遍产出 Markdown 方案文档。

    铁律合规：claude 交互经 ClaudeCodeRunner（已把子进程异常翻译成 StageError），
    本适配器直接上抛，由引擎按 RetryPolicy 重试/收敛 FAILED。方案文档持久化到
    ~/.autodev 之下（git worktree 之外），与 Context 一致。
    """

    def __init__(
        self,
        runner: Callable[[str, Path], str],
        autodev_home: Path,
        id_gen: Callable[[], str] = lambda: uuid.uuid4().hex[:8],
    ) -> None:
        self._runner = runner
        self._home = autodev_home
        self._id_gen = id_gen

    def propose(self, requirement: Requirement, context: ContextArtifact) -> DesignArtifact:
        doc = self._generate(requirement, context)
        path = self._persist(context, requirement, doc)
        return DesignArtifact(design_file=str(path))

    def _generate(self, requirement: Requirement, context: ContextArtifact) -> str:
        prompt = (
            "你在一个代码仓库工作目录里。请先阅读已收集的上下文文档(路径见下), 再只读调查相关代码, "
            "为下述需求产出一份 Markdown 格式的实现方案, 包含以下小节: "
            "`## 方案概述`(一段话说明总体思路), "
            "`## 改动清单`(逐个列出要改/新增的文件, 每个附一行理由), "
            "`## 实现步骤`(有序步骤), "
            "`## 风险与取舍`(潜在风险、被否掉的替代方案)。"
            "只输出 Markdown 文档本身, 不要额外解释; 不要修改任何文件。\n\n"
            f"需求: {requirement.goal}\n\n"
            f"已收集的上下文文档路径(可直接读取): {context.context_file}"
        )
        return self._runner(prompt, Path(context.workspace_location)).strip()

    def _persist(self, context: ContextArtifact, requirement: Requirement, doc: str) -> Path:
        work_item_id = Path(context.workspace_location).name
        d = self._home / "workitems" / work_item_id
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"design-{self._id_gen()}.md"
        header = (
            f"# 实现方案\n\n- 需求: {requirement.goal}\n"
            f"- 分支: {context.workspace_label}\n\n---\n\n"
        )
        path.write_text(header + doc, encoding="utf-8")
        return path
