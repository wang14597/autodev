from __future__ import annotations

from pathlib import Path

import pytest

from autodev.adapters.review_claude import ClaudeReviewAdapter, parse_review_output
from autodev.domain.artifacts import ContextArtifact, DesignArtifact
from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError


def _context(tmp_path: Path) -> ContextArtifact:
    ws = tmp_path / "ws" / "wiabc"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "app.py").write_text("x = 1\n")
    cfile = tmp_path / "home" / "workitems" / "wiabc" / "context-x.md"
    cfile.parent.mkdir(parents=True, exist_ok=True)
    cfile.write_text("## 相关文件\n- app.py\n")
    return ContextArtifact(str(ws), "autodev/wiabc", str(cfile))


DESIGN = DesignArtifact(design_file="/x/design-d1.md")


def test_parse_approved_with_separator():
    approved, comments, body = parse_review_output(
        "REVIEW: APPROVED\n- suggestion: 补个测试\n---\n## 方案概述\n\n改 app.py\n"
    )
    assert approved is True
    assert comments == ("- suggestion: 补个测试",)
    assert body.startswith("## 方案概述")


def test_parse_blocked_collects_blocking_comments():
    approved, comments, body = parse_review_output(
        "REVIEW: BLOCKED\n- blocking: 需求自相矛盾\n---\n"
    )
    assert approved is False
    assert comments == ("- blocking: 需求自相矛盾",)
    assert body == ""


def test_parse_sentinel_without_separator_treats_rest_as_body():
    """缺 --- 分隔符不算格式错误：意见行之后的剩余全部是正文。"""
    approved, comments, body = parse_review_output(
        "REVIEW: APPROVED\n- suggestion: 小改\n## 方案概述\n\n正文\n"
    )
    assert approved is True
    assert comments == ("- suggestion: 小改",)
    assert body.startswith("## 方案概述")


def test_parse_no_separator_does_not_swallow_body_line_that_looks_like_comment():
    """Critical 1（评审打回）：无 `---` 时若正文首行长得像列表项（恰好撞上 comment
    前缀），贪婪匹配会把它错吞进 comments、从正文里永久丢失且不报错。

    修复后：无分隔符时最多认领紧跟哨兵的**一条**意见行，其后一律原样归入正文——
    哪怕它长得也像 `- suggestion:` 开头。退回旧实现（贪婪逐行吞前缀匹配的行）时，
    这条断言会失败：旧实现里第二行被计入 comments、body 里丢了那一行。
    """
    approved, comments, body = parse_review_output(
        "REVIEW: APPROVED\n"
        "- suggestion: 已阅\n"
        "- suggestion: 这其实是正文的第一条列表项\n"
        "\n"
        "更多正文\n"
    )
    assert approved is True
    assert comments == ("- suggestion: 已阅",)
    assert body == "- suggestion: 这其实是正文的第一条列表项\n\n更多正文"


def test_parse_without_sentinel_degrades_to_approved():
    """首行不是哨兵 → 降级为通过、整份当正文。

    降级方向是有意选的：误判通过只多走一次人审，误判回退要烧一次 CAP 配额并重跑数分钟。
    """
    approved, comments, body = parse_review_output("## 方案概述\n\n直接给了方案\n")
    assert approved is True
    assert comments == ()
    assert body.startswith("## 方案概述")


def test_review_persists_final_plan_and_returns_pointer(tmp_path):
    captured = {}

    def runner(prompt: str, cwd: Path) -> str:
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        return "REVIEW: APPROVED\n---\n## 方案概述\n\n最终方案正文\n\n## 评审说明\n\n补了鉴权\n"

    a = ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home", id_gen=lambda: "r1")
    art = a.review(DESIGN, _context(tmp_path))

    assert art.approved is True
    assert art.final_plan_file.endswith("workitems/wiabc/final-plan-r1.md")
    text = Path(art.final_plan_file).read_text()
    assert "最终方案正文" in text
    # 头部只记分支与初稿路径（端口签名拿不到 Requirement，不能写需求）
    assert "autodev/wiabc" in text
    assert "/x/design-d1.md" in text
    # 提示词把两份文档的绝对路径都给了 CLI，cwd 是 worktree
    assert str(_context(tmp_path).context_file) in captured["prompt"]
    assert "/x/design-d1.md" in captured["prompt"]
    assert captured["cwd"] == tmp_path / "ws" / "wiabc"


def test_review_approved_but_empty_body_is_logic_error(tmp_path):
    """通过却没给方案 → LOGIC 失败。空方案绝不能交下游。"""

    def runner(prompt: str, cwd: Path) -> str:
        return "REVIEW: APPROVED\n---\n   \n"

    a = ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home")
    with pytest.raises(StageError) as e:
        a.review(DESIGN, _context(tmp_path))
    assert e.value.failure_kind is FailureKind.LOGIC


def test_review_blocked_with_empty_body_does_not_persist(tmp_path):
    """判回退时没有终稿可言：不落盘、指针为空，下游按 Task 4 的兜底退回初稿。"""

    def runner(prompt: str, cwd: Path) -> str:
        return "REVIEW: BLOCKED\n- blocking: 上下文缺关键信息\n"

    a = ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home")
    art = a.review(DESIGN, _context(tmp_path))
    assert art.approved is False
    assert art.final_plan_file == ""
    assert art.comments == ("- blocking: 上下文缺关键信息",)


def test_review_blocked_with_nonempty_body_still_does_not_persist(tmp_path):
    """Important 2（评审打回）：不变式是 final_plan_file 非空 ⟺ 评审通过。

    即使模型判了 BLOCKED 却仍附了一份正文，也不能落盘 / 不能返回非空指针——否则
    下游得先看 approved 再看指针才能确认"这是不是权威终稿"，多一次判断就多一次
    把半成品当终稿的风险。被否理由已由 comments 承载，不需要那份正文。
    """

    def runner(prompt: str, cwd: Path) -> str:
        return "REVIEW: BLOCKED\n- blocking: 需求自相矛盾\n---\n## 方案概述\n\n仍给了正文\n"

    a = ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home")
    art = a.review(DESIGN, _context(tmp_path))
    assert art.approved is False
    assert art.final_plan_file == ""
    assert art.comments == ("- blocking: 需求自相矛盾",)
    # 且确实没有落盘任何 final-plan 文件（不是只清空了指针，落盘动作本身没发生）。
    workitems_dir = tmp_path / "home" / "workitems" / "wiabc"
    assert not list(workitems_dir.glob("final-plan-*.md"))


def test_review_propagates_stage_error(tmp_path):
    """铁律 3：runner 已翻译好的失败直接上抛，适配器不吞不重试。"""

    def runner(prompt: str, cwd: Path) -> str:
        raise StageError(FailureKind.TRANSIENT, "claude 超时")

    a = ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home")
    with pytest.raises(StageError) as e:
        a.review(DESIGN, _context(tmp_path))
    assert e.value.failure_kind is FailureKind.TRANSIENT
