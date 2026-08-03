# src/autodev/adapters/review_claude.py
"""ReviewPort 真实实现：方案评审产出**最终方案**文档。

REVIEW 在本平台是"精炼"而非"判决"：读上下文与方案两份文档、只读核对真实代码，
产出一份可直接交给下游的最终方案。判回退（approved=False）收窄到"问题不在方案层面
而在上游"——需求自相矛盾、上下文缺关键信息、方案方向根本错需重新调研。

铁律合规：claude 交互经 ClaudeCodeRunner（已把子进程异常翻译成 StageError），本适配器
直接上抛，由引擎按 RetryPolicy 重试/回退/收敛 FAILED；文档落盘在 ~/.autodev 之下
（git worktree 之外），与 Context/Design 一致。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from autodev.domain.artifacts import ContextArtifact, DesignArtifact, ReviewArtifact
from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError

_APPROVED = "REVIEW: APPROVED"
_BLOCKED = "REVIEW: BLOCKED"
_SEPARATOR = "---"
_COMMENT_PREFIXES = ("- blocking:", "- suggestion:")


def parse_review_output(raw: str) -> tuple[bool, tuple[str, ...], str]:
    """把评审输出解析成 (approved, comments, 最终方案正文)。

    约定格式：首行哨兵 → 若干意见行 → `---` → 正文。ClaudeCodeRunner 只回 stdout 文本，
    没有 tool_use 那种强制 schema 可用，故用哨兵。

    首行不是哨兵时**降级**为通过、整份当正文：误判通过的代价是多走一次 REVIEW_GATE
    人审，误判回退的代价是烧掉一次 RetryPolicy 的 CAP 配额并重跑一次数分钟的 DESIGN。
    前者明显更轻，所以降级往通过那边倒。

    comments 的采集与 approved 无关，且**保留 `- blocking:` / `- suggestion:` 前缀原样**，
    让 UI 与人一眼看出哪条是拦路的、哪条只是建议。
    """
    text = raw.strip()
    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    if first not in (_APPROVED, _BLOCKED):
        return True, (), text

    approved = first == _APPROVED
    comments: list[str] = []
    i = 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == _SEPARATOR:
            i += 1
            break
        if stripped.startswith(_COMMENT_PREFIXES):
            comments.append(stripped)
            i += 1
            continue
        if not stripped:
            i += 1
            continue
        # 非空、非意见行、非分隔符 → 正文从这一行开始（缺 --- 不算格式错误）
        break
    body = "\n".join(lines[i:]).strip()
    return approved, tuple(comments), body


class ClaudeReviewAdapter:
    """在 worktree 内只读单遍跑 claude，产出最终方案文档。"""

    def __init__(
        self,
        runner: Callable[[str, Path], str],
        autodev_home: Path,
        id_gen: Callable[[], str] = lambda: uuid.uuid4().hex[:8],
    ) -> None:
        self._runner = runner
        self._home = autodev_home
        self._id_gen = id_gen

    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact:
        raw = self._runner(self._prompt(design, context), Path(context.workspace_location))
        approved, comments, body = parse_review_output(raw)
        if approved and not body:
            # 通过却没给方案：空方案绝不交下游。LOGIC → 回退重设计。
            raise StageError(FailureKind.LOGIC, "评审判定通过但未产出最终方案正文")
        if not body:
            # 判回退时没有终稿可言，不落空文件；下游兜底退回 DESIGN 初稿。
            return ReviewArtifact(approved, comments, final_plan_file="")
        path = self._persist(design, context, body)
        return ReviewArtifact(approved, comments, final_plan_file=str(path))

    def _prompt(self, design: DesignArtifact, context: ContextArtifact) -> str:
        return (
            "你在一个代码仓库工作目录里, 担任方案评审员。请依次:\n"
            f"1. 读已收集的上下文文档: {context.context_file}\n"
            f"2. 读待评审的实现方案初稿: {design.design_file}\n"
            "3. 只读调查真实代码核对方案: 提到的文件是否存在, 接口签名是否如其所述, "
            "是否与现有架构冲突, 是否违反项目约定(如仓库根目录 CLAUDE.md 所载)。\n"
            "4. 产出一份**最终方案**。能自己补全/纠正的问题直接改进到最终稿里, "
            "不要动辄打回。\n\n"
            "输出格式(严格遵守):\n"
            "首行必须是 `REVIEW: APPROVED` 或 `REVIEW: BLOCKED`。"
            "仅当问题不在方案层面而在上游(需求自相矛盾 / 上下文缺关键信息 / "
            "方案方向根本错需重新调研)才用 BLOCKED。\n"
            "首行之后可跟若干意见行, 每行以 `- blocking: ` 或 `- suggestion: ` 开头。\n"
            f"然后单独一行 `{_SEPARATOR}`, 其后是最终方案的 Markdown 正文, 含小节 "
            "`## 方案概述` / `## 改动清单` / `## 实现步骤` / `## 风险与取舍` / `## 评审说明`"
            "(最后一节说明相对初稿改了什么、为什么)。\n"
            "不要修改任何文件; 除上述内容外不要输出别的解释。"
        )

    def _persist(self, design: DesignArtifact, context: ContextArtifact, body: str) -> Path:
        work_item_id = Path(context.workspace_location).name
        d = self._home / "workitems" / work_item_id
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"final-plan-{self._id_gen()}.md"
        # 头部只记分支与初稿路径（供溯源"这份终稿评审的是哪一版初稿"）。
        # 端口签名拿不到 Requirement，故不记需求——需求已在初稿与上下文文档里。
        header = (
            f"# 最终方案\n\n- 分支: {context.workspace_label}\n"
            f"- 初稿: {design.design_file}\n\n---\n\n"
        )
        path.write_text(header + body, encoding="utf-8")
        return path
