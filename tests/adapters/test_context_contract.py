"""ContextPort 端口一致性契约: FakeContext 与真实 ClaudeContextAdapter(注入假 runner)
必须满足同一套调用者可依赖的行为——返回携带请求的 workspace_label、非空
context_file(指针)、非空 workspace_location 的 ContextArtifact。

外加一个 @pytest.mark.live 的真调 claude 冒烟, 默认(不带 AUTODEV_LIVE=1)跳过,
不参与常规 CI/本地全量门禁。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from autodev.adapters.context_claude import ClaudeContextAdapter
from autodev.domain.value_objects import Requirement, WorkspaceHandle
from tests.fakes import FakeContext

REQ = Requirement("fix login", "repo-a", (), "raw")


def _handle(tmp_path: Path) -> WorkspaceHandle:
    ws = tmp_path / "ws" / "wiabc"
    ws.mkdir(parents=True)
    (ws / "app.py").write_text("x = 1\n")
    return WorkspaceHandle(location=str(ws), label="autodev/wiabc")


@pytest.fixture(params=["fake", "real"])
def adapter(request, tmp_path):
    if request.param == "fake":
        return FakeContext()

    def runner(prompt: str, cwd: Path) -> str:
        return "## 相关文件\n\n- `app.py`: 应用入口\n\n## 现状理解\n\ns\n\n## 改动要点\n\n(无)\n"

    return ClaudeContextAdapter(runner=runner, autodev_home=tmp_path / "home")


def test_gather_returns_context_artifact_with_pointer(adapter, tmp_path):
    art = adapter.gather(REQ, _handle(tmp_path))
    assert art.workspace_label == "autodev/wiabc"
    assert art.context_file  # 非空指针
    assert art.workspace_location


@pytest.mark.live
def test_live_gather_against_real_claude(tmp_path):
    if not os.environ.get("AUTODEV_LIVE"):
        pytest.skip("live 测试需 AUTODEV_LIVE=1 + 可用 claude/网关")
    from autodev.adapters.claude_runner import ClaudeCodeRunner

    ws = tmp_path / "ws" / "wilive"
    ws.mkdir(parents=True)
    (ws / "app.py").write_text("def login(): ...\n")
    r = ClaudeCodeRunner()
    a = ClaudeContextAdapter(
        runner=lambda p, c: r.run(p, c, "plan"), autodev_home=tmp_path / "home"
    )
    art = a.gather(
        Requirement("检查 login", "x", (), "raw"),
        WorkspaceHandle(location=str(ws), label="autodev/wilive"),
    )
    assert Path(art.context_file).read_text().strip()  # 非空
