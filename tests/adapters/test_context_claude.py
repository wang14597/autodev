import json
from pathlib import Path

import pytest

from autodev.adapters.context_claude import ClaudeContextAdapter
from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError
from autodev.domain.value_objects import Requirement, WorkspaceHandle

REQ = Requirement("fix login", "repo-a", (), "raw")


def _handle(tmp_path):
    ws = tmp_path / "ws" / "wi12345678"
    ws.mkdir(parents=True)
    return WorkspaceHandle(location=str(ws), label="autodev/wi12345678")


def test_gather_parses_json_and_writes_markdown(tmp_path):
    def runner(prompt, cwd):
        return json.dumps({"relevant_files": ["src/login.py"], "summary": "登录逻辑在 login.py"})

    home = tmp_path / "home"
    a = ClaudeContextAdapter(runner=runner, autodev_home=home, id_gen=lambda: "aaa")
    art = a.gather(REQ, _handle(tmp_path))
    p = Path(art.context_file)
    assert p.exists() and p.suffix == ".md"
    assert "登录逻辑在 login.py" in p.read_text() and "src/login.py" in p.read_text()
    assert str(home) in art.context_file  # 写在 autodev_home 下
    assert "/ws/wi12345678" not in art.context_file  # 不在 worktree 内
    assert art.workspace_label == "autodev/wi12345678"


def test_gather_degrades_on_non_json(tmp_path):
    def runner(prompt, cwd):
        return "这是一段自由文本, 不是 JSON"

    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: "b")
    art = a.gather(REQ, _handle(tmp_path))
    txt = Path(art.context_file).read_text()
    assert "这是一段自由文本" in txt  # summary 降级为原文


def test_gather_propagates_collect_failure(tmp_path):
    def runner(prompt, cwd):
        raise StageError(FailureKind.TRANSIENT, "claude 挂了")

    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h")
    with pytest.raises(StageError):
        a.gather(REQ, _handle(tmp_path))


def test_gather_multiple_writes_distinct_files(tmp_path):
    def runner(prompt, cwd):
        return json.dumps({"relevant_files": [], "summary": "s"})

    ids = iter(["x1", "x2"])
    a = ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "h", id_gen=lambda: next(ids))
    h = _handle(tmp_path)
    a1 = a.gather(REQ, h)
    a2 = a.gather(REQ, h)
    assert a1.context_file != a2.context_file  # 不覆盖
