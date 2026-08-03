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

import re
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
# 整份输出被套一层围栏时的首行形态：``` 或 ```<语言标记>（无其余字符）。
_FENCE_FIRST_LINE = re.compile(r"^```[^\s`]*$")


def _strip_outer_fence(text: str) -> str:
    """剥掉模型给整份输出套的最外层 ``` / ```<语言标记> 围栏（如 ```markdown）。

    本仓库已确认模型会时不时给整份评审输出套一层 ```markdown 围栏（前端
    `frontend/src/lib/markdown.ts` 的 `unwrapMarkdownFence` 正是为同一现象写的）。
    若不在解析前剥离，`splitlines()[0]` 恒是围栏行、不等于任何哨兵，`REVIEW: BLOCKED`
    永远无法被识别。

    规则严格且保守：仅当首行整体是 ``` 或 ```<语言标记>、且末行整体是 ``` 时才剥离
    首尾两行；其余一切原样保留——尤其是正文内部真实的代码围栏（```python 等），
    它们既不在首行也不在末行，不受影响。
    """
    lines = text.splitlines()
    if len(lines) >= 2 and _FENCE_FIRST_LINE.match(lines[0].strip()) and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return text


def parse_review_output(raw: str) -> tuple[bool, tuple[str, ...], str]:
    """把评审输出解析成 (approved, comments, 最终方案正文)。

    约定格式：首行哨兵 → 若干意见行 → `---` → 正文。ClaudeCodeRunner 只回 stdout 文本，
    没有 tool_use 那种强制 schema 可用，故用哨兵。

    首行不是哨兵时**降级**为通过、整份当正文：误判通过的代价是多走一次 REVIEW_GATE
    人审，误判回退的代价是烧掉一次 RetryPolicy 的 CAP 配额并重跑一次数分钟的 DESIGN。
    前者明显更轻，所以降级往通过那边倒。

    comments 的采集与 approved 无关，且**保留 `- blocking:` / `- suggestion:` 前缀原样**，
    让 UI 与人一眼看出哪条是拦路的、哪条只是建议。

    分隔符的识别范围**限定在紧跟哨兵的前导块内**：从哨兵之后逐行扫描，只跨过空行与
    `- blocking:` / `- suggestion:` 意见行，找到第一个既非空行也非意见行的行——若它整体是
    `---`，那就是真分隔符（其前的意见行悉数采信，其后原样整体作为正文）。

    若前导块里没能找到紧邻的分隔符，则分两种情况：
    - **全文（含正文深处）都没有任何 `---`**：安全场景，退回保守的
      `_collect_leading_comment`——只认领紧跟哨兵的第一条意见行，其余原样归入正文
      （宁可漏判一条真实意见，也绝不丢正文行）。
    - **全文深处存在 `---`**（提示词要求正文含 `## 风险与取舍` 这类小节，出现 Markdown
      水平线完全正常）：这条 `---` 不是紧邻前导块的真分隔符，不可信——不再对任何前导行
      猜测是否为意见行，整段原样归入正文、`comments` 为空。否则若正文首行恰好长得像
      `- suggestion: ...` 列表项，会被误当意见行吞掉、从持久化终稿里静默消失。
    """
    text = _strip_outer_fence(raw.strip()).strip()
    lines = text.splitlines()
    first = lines[0].strip() if lines else ""
    if first not in (_APPROVED, _BLOCKED):
        return True, (), text

    approved = first == _APPROVED
    rest = lines[1:]

    i = 0
    while i < len(rest):
        stripped = rest[i].strip()
        if not stripped or stripped.startswith(_COMMENT_PREFIXES):
            i += 1
            continue
        break

    if i < len(rest) and rest[i].strip() == _SEPARATOR:
        comment_lines = tuple(
            ln.strip() for ln in rest[:i] if ln.strip().startswith(_COMMENT_PREFIXES)
        )
        body = "\n".join(rest[i + 1 :]).strip()
        return approved, comment_lines, body

    if not any(ln.strip() == _SEPARATOR for ln in rest):
        leading_comment, body = _collect_leading_comment(rest)
        return approved, leading_comment, body

    # 深处存在 --- 但前导块内没有紧邻它：不可信，不猜任何前导行，整段原样归正文。
    return approved, (), "\n".join(rest).strip()


def _collect_leading_comment(lines: list[str]) -> tuple[tuple[str, ...], str]:
    """无 `---` 时的保守取舍：最多认领紧跟哨兵的**一条**意见行，其余全部当正文。

    见 `parse_review_output` docstring：没有分隔符就无法可靠区分"后续意见行"与
    "长得像列表项的正文首行"。跳过哨兵后的前导空行，若第一条非空行匹配意见前缀，
    仅收它一条为 comment，其后所有行（无论是否也长得像意见行）都原样并入正文。
    """
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip().startswith(_COMMENT_PREFIXES):
        comment = lines[i].strip()
        body = "\n".join(lines[i + 1 :]).strip()
        return (comment,), body
    return (), "\n".join(lines).strip()


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
        if not approved:
            # 判回退没有终稿可言：无论模型是否仍给了正文都不落盘。不变式：
            # final_plan_file 非空 ⟺ 评审通过——下游一个真值判断就不会把判了回退的
            # 半成品当权威终稿。被否理由由 comments 承载，不需要那份正文。
            return ReviewArtifact(approved, comments, final_plan_file="")
        if not body:
            # 通过却没给方案：空方案绝不交下游。LOGIC → 回退重设计。
            raise StageError(FailureKind.LOGIC, "评审判定通过但未产出最终方案正文")
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
