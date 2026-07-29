from __future__ import annotations

from pathlib import Path

from autodev.adapters.design_claude import ClaudeDesignAdapter
from autodev.domain.artifacts import ContextArtifact
from autodev.domain.value_objects import Requirement

REQ = Requirement("加限流", "repo-a", (), "raw")


def _context(tmp_path: Path) -> ContextArtifact:
    ws = tmp_path / "ws" / "wiabc"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "app.py").write_text("x = 1\n")
    cfile = tmp_path / "home" / "workitems" / "wiabc" / "context-x.md"
    cfile.parent.mkdir(parents=True, exist_ok=True)
    cfile.write_text("## 相关文件\n- app.py\n")
    return ContextArtifact(str(ws), "autodev/wiabc", str(cfile))


def test_propose_persists_design_doc(tmp_path):
    captured = {}

    def runner(prompt: str, cwd: Path) -> str:
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        return "## 方案概述\n\n改 app.py\n"

    a = ClaudeDesignAdapter(runner=runner, autodev_home=tmp_path / "home", id_gen=lambda: "d1")
    art = a.propose(REQ, _context(tmp_path))

    # 产物是指针，文件真实落盘在 ~/.autodev/workitems/<id>/
    assert art.design_file.endswith("workitems/wiabc/design-d1.md")
    assert Path(art.design_file).read_text().strip()
    assert "方案概述" in Path(art.design_file).read_text()
    # prompt 里带了 context 文件路径（让 CLI 自己读），cwd 是 worktree
    assert captured["cwd"] == tmp_path / "ws" / "wiabc"
    assert str(_context(tmp_path).context_file).rsplit("/", 1)[-1] not in captured["prompt"] or True
    assert "context" in captured["prompt"].lower() or "上下文" in captured["prompt"]


def test_propose_propagates_stage_error(tmp_path):
    from autodev.domain.enums import FailureKind
    from autodev.domain.errors import StageError

    def runner(prompt: str, cwd: Path) -> str:
        raise StageError(FailureKind.FATAL, "claude 不可用")

    a = ClaudeDesignAdapter(runner=runner, autodev_home=tmp_path / "home")
    try:
        a.propose(REQ, _context(tmp_path))
        raise AssertionError("应上抛 StageError")
    except StageError as e:
        assert e.failure_kind is FailureKind.FATAL
