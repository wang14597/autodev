from pathlib import Path

import pytest

from autodev.adapters.context_claude import ClaudeContextAdapter
from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError
from autodev.domain.value_objects import Requirement, WorkspaceHandle

REQ = Requirement("fix login", "repo-a", (), "raw")

FIRST_PASS_DOC = (
    "## 相关文件\n\n- `src/login.py`: 登录入口\n\n"
    "## 现状理解\n\n登录逻辑在 login.py 里。\n\n"
    "## 改动要点\n\n需要调整校验逻辑。\n"
)

IMPROVED_DOC = (
    "## 相关文件\n\n- `src/login.py`: 登录入口\n- `src/auth.py`: 鉴权辅助\n\n"
    "## 现状理解\n\n登录逻辑在 login.py 里, 依赖 auth.py 做鉴权。改进版更完整。\n\n"
    "## 改动要点\n\n需要调整校验逻辑, 并同步更新 auth.py。\n"
)


def _handle(tmp_path):
    ws = tmp_path / "ws" / "wi12345678"
    ws.mkdir(parents=True)
    return WorkspaceHandle(location=str(ws), label="autodev/wi12345678")


def test_gather_persists_collected_markdown(tmp_path):
    def runner(prompt, cwd):
        return FIRST_PASS_DOC

    home = tmp_path / "home"
    a = ClaudeContextAdapter(runner=runner, autodev_home=home, id_gen=lambda: "aaa")
    art = a.gather(REQ, _handle(tmp_path))
    p = Path(art.context_file)
    assert p.exists() and p.suffix == ".md"
    text = p.read_text()
    assert "src/login.py" in text
    assert "登录逻辑在 login.py" in text
    assert str(home) in art.context_file  # 写在 autodev_home 下
    assert "/ws/wi12345678" not in art.context_file  # 不在 worktree 内
    assert art.workspace_label == "autodev/wi12345678"


def test_gather_propagates_collect_failure(tmp_path):
    def runner(prompt, cwd):
        raise StageError(FailureKind.TRANSIENT, "claude 挂了")

    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h")
    with pytest.raises(StageError):
        a.gather(REQ, _handle(tmp_path))


def test_review_improves_result(tmp_path):
    outs = iter([FIRST_PASS_DOC, IMPROVED_DOC])

    def runner(prompt, cwd):
        return next(outs)

    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: "r1")
    art = a.gather(REQ, _handle(tmp_path))
    txt = Path(art.context_file).read_text()
    assert "改进版" in txt and "src/auth.py" in txt  # 反映复核改进


def test_review_failure_degrades_to_first_pass(tmp_path):
    calls = {"n": 0}

    def runner(prompt, cwd):
        calls["n"] += 1
        if calls["n"] == 1:
            return FIRST_PASS_DOC
        raise StageError(FailureKind.TRANSIENT, "复核挂了")  # runner 已重试耗尽后抛

    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: "r2")
    art = a.gather(REQ, _handle(tmp_path))
    txt = Path(art.context_file).read_text()
    assert "登录逻辑在 login.py" in txt  # 降级回第一遍, 不抛
    assert "改进版" not in txt


def test_review_empty_output_degrades_to_first_pass(tmp_path):
    outs = iter([FIRST_PASS_DOC, ""])

    def runner(prompt, cwd):
        return next(outs)

    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: "r3")
    art = a.gather(REQ, _handle(tmp_path))
    txt = Path(art.context_file).read_text()
    assert "登录逻辑在 login.py" in txt  # 第一遍内容被保留


def test_review_too_short_output_degrades_to_first_pass(tmp_path):
    outs = iter([FIRST_PASS_DOC, "嗯"])  # 过短/退化输出

    def runner(prompt, cwd):
        return next(outs)

    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: "r4")
    art = a.gather(REQ, _handle(tmp_path))
    txt = Path(art.context_file).read_text()
    assert "登录逻辑在 login.py" in txt


def test_gather_multiple_writes_distinct_files(tmp_path):
    def runner(prompt, cwd):
        return FIRST_PASS_DOC

    ids = iter(["x1", "x2"])
    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: next(ids))
    h = _handle(tmp_path)
    a1 = a.gather(REQ, h)
    a2 = a.gather(REQ, h)
    assert a1.context_file != a2.context_file  # 不覆盖
