"""演示组合根的 HTTP 集成测试（切片 2.1）：为 agent-browser E2E 提供后端保证。

同时守护安全立场：生产组合根的 Execution/Verification 端口必须仍是抛错桩。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
    """安全回归守卫：沙箱就绪（迭代 2.4）前，生产绝不接真实 Execution/Verification。"""
    monkeypatch.setenv("AUTODEV_HOME", str(tmp_path))
    from autodev.webapp.config import build_env_service
    from autodev.webapp.stubs import UnavailableStage

    ctx = build_env_service()._engine.ctx
    assert isinstance(ctx.executor, UnavailableStage)
    assert isinstance(ctx.verifier, UnavailableStage)
    assert isinstance(ctx.designer, UnavailableStage)
