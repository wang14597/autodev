"""ReviewPort 端口一致性契约：演示评审端口与真实适配器(注入假 runner)必须都返回
approved 为真、且携带非空最终方案指针的 ReviewArtifact。外加一个 @pytest.mark.live
真调 claude 冒烟(默认跳过)。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from autodev.adapters.demo import DemoReview
from autodev.adapters.review_claude import ClaudeReviewAdapter
from autodev.domain.artifacts import ContextArtifact, DesignArtifact


def _context(tmp_path: Path) -> ContextArtifact:
    ws = tmp_path / "ws" / "wiabc"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "app.py").write_text("x = 1\n")
    cfile = tmp_path / "home" / "workitems" / "wiabc" / "context-x.md"
    cfile.parent.mkdir(parents=True, exist_ok=True)
    cfile.write_text("## 相关文件\n- app.py\n")
    return ContextArtifact(str(ws), "autodev/wiabc", str(cfile))


def _design(tmp_path: Path) -> DesignArtifact:
    dfile = tmp_path / "home" / "workitems" / "wiabc" / "design-d1.md"
    dfile.parent.mkdir(parents=True, exist_ok=True)
    dfile.write_text("## 方案概述\n\n改 app.py\n")
    return DesignArtifact(design_file=str(dfile))


@pytest.fixture(params=["fake", "real"])
def adapter(request, tmp_path):
    if request.param == "fake":
        return DemoReview()

    def runner(prompt: str, cwd: Path) -> str:
        return "REVIEW: APPROVED\n---\n## 方案概述\n\n最终方案\n"

    return ClaudeReviewAdapter(runner=runner, autodev_home=tmp_path / "home")


def test_review_returns_artifact_with_final_plan_pointer(adapter, tmp_path):
    art = adapter.review(_design(tmp_path), _context(tmp_path))
    assert art.approved is True
    assert art.final_plan_file  # 非空指针
    assert Path(art.final_plan_file).read_text().strip()


@pytest.mark.live
def test_live_review_against_real_claude(tmp_path):
    if not os.environ.get("AUTODEV_LIVE"):
        pytest.skip("live 测试需 AUTODEV_LIVE=1 + 可用 claude/网关")
    from autodev.adapters.claude_runner import ClaudeCodeRunner

    r = ClaudeCodeRunner()
    a = ClaudeReviewAdapter(runner=lambda p, c: r.run(p, c, "plan"), autodev_home=tmp_path / "home")
    art = a.review(_design(tmp_path), _context(tmp_path))
    assert art.final_plan_file
    assert Path(art.final_plan_file).read_text().strip()
