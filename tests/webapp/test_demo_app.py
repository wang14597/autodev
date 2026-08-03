"""演示组合根的 HTTP 集成测试（切片 2.1）：为 agent-browser E2E 提供后端保证。

同时守护安全立场：生产组合根的 Execution/Verification 端口必须仍是抛错桩。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autodev.adapters.design_claude import ClaudeDesignAdapter
from autodev.adapters.review_claude import ClaudeReviewAdapter
from autodev.webapp.demo_config import build_demo_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AUTODEV_HOME", str(tmp_path))
    return TestClient(build_demo_app())


def _create_project(client: TestClient, name: str = "demo-proj") -> str:
    resp = client.post("/api/projects", json={"name": name, "repo": "demo://repo"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _create_workitem(
    client: TestClient, pid: str, goal: str, autonomy_enabled: bool = False
) -> str:
    resp = client.post(
        f"/api/projects/{pid}/workitems",
        json={"goal": goal, "autonomy_enabled": autonomy_enabled},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_low_risk_workitem_reaches_done_via_api(client: TestClient) -> None:
    pid = _create_project(client)
    wid = _create_workitem(client, pid, "fix typo in README", autonomy_enabled=True)
    detail = client.get(f"/api/workitems/{wid}").json()
    assert detail["state"] == "DONE"
    assert detail["triage"]["risk"] == "LOW"


def test_high_risk_workitem_suspends_with_high_risk_badge(client: TestClient) -> None:
    pid = _create_project(client)
    wid = _create_workitem(
        client,
        pid,
        "migrate auth to new credential store and delete old tokens",
        autonomy_enabled=True,
    )
    detail = client.get(f"/api/workitems/{wid}").json()
    assert detail["state"] == "WAIT_HUMAN"
    assert detail["triage"]["risk"] == "HIGH"
    assert detail["triage"]["signals"]  # 可解释依据非空


def test_disabled_workitem_stops_at_context_gate(client: TestClient) -> None:
    pid = _create_project(client)
    wid = _create_workitem(client, pid, "fix typo in README")  # 默认关
    detail = client.get(f"/api/workitems/{wid}").json()
    assert detail["state"] == "WAIT_HUMAN"
    assert detail["pending_gate"] == "CONTEXT_GATE"


def test_decide_close_collect_only_done(client: TestClient) -> None:
    pid = _create_project(client)
    wid = _create_workitem(client, pid, "fix typo in README")  # 默认关 → 停 CONTEXT_GATE
    client.post(f"/api/workitems/{wid}/decide", json={"action": "close"})
    detail = client.get(f"/api/workitems/{wid}").json()
    assert detail["state"] == "DONE"
    assert detail["collect_only"] is True


def test_approve_endpoint_progresses_high_risk_item(client: TestClient) -> None:
    pid = _create_project(client)
    wid = _create_workitem(
        client, pid, "delete the legacy credential tokens", autonomy_enabled=True
    )
    assert client.get(f"/api/workitems/{wid}").json()["state"] == "WAIT_HUMAN"

    # 两个门都挂起（纵深防御）——批准两次到 DONE。
    client.post(f"/api/workitems/{wid}/approve", json={"approved": True})
    assert client.get(f"/api/workitems/{wid}").json()["state"] == "WAIT_HUMAN"
    client.post(f"/api/workitems/{wid}/approve", json={"approved": True})
    assert client.get(f"/api/workitems/{wid}").json()["state"] == "DONE"


def test_production_execution_and_verification_remain_stubs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """安全回归守卫：沙箱就绪前，生产绝不接真实 Execution/Verification/Delivery。"""
    monkeypatch.setenv("AUTODEV_HOME", str(tmp_path))
    from autodev.adapters.triage_llm import LlmTriageAdapter
    from autodev.webapp.config import build_env_service
    from autodev.webapp.stubs import UnavailableStage

    ctx = build_env_service()._engine.ctx
    # 分诊/方案设计/方案评审已是真实适配器；Execution/Verification/Delivery 在沙箱
    # 就绪前仍须为桩。
    assert isinstance(ctx.triage, LlmTriageAdapter)
    assert isinstance(ctx.executor, UnavailableStage)
    assert isinstance(ctx.verifier, UnavailableStage)
    assert isinstance(ctx.delivery, UnavailableStage)
    assert isinstance(ctx.designer, ClaudeDesignAdapter)
    assert isinstance(ctx.reviewer, ClaudeReviewAdapter)


def test_implemented_stages_matches_real_ports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """防漂移守卫：能力集合必须与生产组合根里"端口是否为桩"逐阶段一致。

    这是本次设计要消灭的根因——同一事实多处手抄。谁加了真适配器却忘了更新集合，
    这里就红。局限：下面的 stage→port 映射本身仍是手工维护的，但它住在测试里，
    漂移的后果是测试大声失败，而不是线上静默错标「待建设」。
    """
    monkeypatch.setenv("AUTODEV_HOME", str(tmp_path))
    from autodev.domain.enums import WorkflowState as S
    from autodev.webapp.config import build_env_service
    from autodev.webapp.drive import IMPLEMENTED_STAGES
    from autodev.webapp.stubs import UnavailableStage

    # INTAKE / ACCEPT 的处理器是纯函数（不碰端口），不参与本断言。
    stage_port = {
        S.TRIAGE: "triage",
        S.CONTEXT: "gatherer",
        S.DESIGN: "designer",
        S.REVIEW: "reviewer",
        S.IMPL: "executor",
        S.VERIFY: "verifier",
        S.SUBMIT_MR: "delivery",
    }
    ctx = build_env_service()._engine.ctx
    for stage, port_name in stage_port.items():
        port_is_real = not isinstance(getattr(ctx, port_name), UnavailableStage)
        assert (stage in IMPLEMENTED_STAGES) == port_is_real, (
            f"{stage.name}: 能力集合认为 {stage in IMPLEMENTED_STAGES}，"
            f"而端口 ctx.{port_name} 实况为 {'真实' if port_is_real else '桩'}"
        )
