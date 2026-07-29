"""DesignPort 端口一致性契约：DemoDesign 与真实 ClaudeDesignAdapter(注入假 runner)
必须都返回携带非空 design_file 指针的 DesignArtifact。外加一个 @pytest.mark.live 真调
claude 冒烟(默认跳过)。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from autodev.adapters.demo import DemoDesign
from autodev.adapters.design_claude import ClaudeDesignAdapter
from autodev.domain.artifacts import ContextArtifact
from autodev.domain.value_objects import Requirement

REQ = Requirement("加限流", "repo-a", (), "raw")


def _context(tmp_path: Path) -> ContextArtifact:
    ws = tmp_path / "ws" / "wiabc"
    ws.mkdir(parents=True)
    (ws / "app.py").write_text("x = 1\n")
    cfile = tmp_path / "home" / "workitems" / "wiabc" / "context-x.md"
    cfile.parent.mkdir(parents=True)
    cfile.write_text("## 相关文件\n- app.py\n")
    return ContextArtifact(str(ws), "autodev/wiabc", str(cfile))


@pytest.fixture(params=["fake", "real"])
def adapter(request, tmp_path):
    if request.param == "fake":
        return DemoDesign()

    def runner(prompt: str, cwd: Path) -> str:
        return "## 方案概述\n\n改 app.py\n\n## 改动清单\n\n- `app.py`: 入口\n"

    return ClaudeDesignAdapter(runner=runner, autodev_home=tmp_path / "home")


def test_propose_returns_design_artifact_with_pointer(adapter, tmp_path):
    art = adapter.propose(REQ, _context(tmp_path))
    assert art.design_file  # 非空指针


@pytest.mark.live
def test_live_propose_against_real_claude(tmp_path):
    if not os.environ.get("AUTODEV_LIVE"):
        pytest.skip("live 测试需 AUTODEV_LIVE=1 + 可用 claude/网关")
    from autodev.adapters.claude_runner import ClaudeCodeRunner

    ctx = _context(tmp_path)
    r = ClaudeCodeRunner()
    a = ClaudeDesignAdapter(runner=lambda p, c: r.run(p, c, "plan"), autodev_home=tmp_path / "home")
    art = a.propose(Requirement("给 app.py 加个 hello 函数", "x", (), "raw"), ctx)
    assert Path(art.design_file).read_text().strip()
