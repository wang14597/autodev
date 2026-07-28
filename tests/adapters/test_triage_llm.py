"""LlmTriageAdapter 契约测试：注入假 httpx 客户端,无网络跑同一组断言。

另有一个 @pytest.mark.live 冒烟(默认跳过,AUTODEV_LIVE=1 才真打网关/模型)。
"""

from __future__ import annotations

import os

import httpx
import pytest

from autodev.adapters.triage_llm import LlmTriageAdapter, _auth_headers_from_env
from autodev.domain.enums import RiskLevel, TaskType, TriageIntent
from autodev.domain.errors import StageError
from autodev.domain.value_objects import Requirement, TriageSignal


def _req(goal: str = "delete old credential tokens") -> Requirement:
    return Requirement(goal, "repo-a", (), goal)


class _FakeResp:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self._status = status

    def raise_for_status(self) -> None:
        if self._status >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, resp=None, exc: Exception | None = None) -> None:
        self._resp = resp
        self._exc = exc
        self.calls: list[dict] = []

    def post(self, url, *, headers, json):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self._exc is not None:
            raise self._exc
        return self._resp


def _tool_use_payload(**overrides) -> dict:
    inp = {
        "level": "MEDIUM_FEATURE",
        "risk": "HIGH",
        "intent": "CONSULTATION",
        "confidence": 0.7,
        "signals": ["keyword:delete"],
    }
    inp.update(overrides)
    return {
        "model": "claude-opus-4-8",
        "content": [{"type": "tool_use", "name": "record_triage", "input": inp}],
    }


def _adapter(client) -> LlmTriageAdapter:
    return LlmTriageAdapter(client, "claude-opus-4-8", "http://gw/api", {"x-api-key": "k"})


def test_parses_tool_use_into_triage_signal():
    sig = _adapter(_FakeClient(_FakeResp(_tool_use_payload()))).classify(_req())
    assert isinstance(sig, TriageSignal)
    assert sig.level is TaskType.MEDIUM_FEATURE
    assert sig.risk is RiskLevel.HIGH
    assert sig.intent is TriageIntent.CONSULTATION
    assert sig.confidence == 0.7
    assert sig.signals == ("keyword:delete",)


def test_posts_to_v1_messages_with_forced_tool_choice_and_auth():
    client = _FakeClient(_FakeResp(_tool_use_payload()))
    _adapter(client).classify(_req())
    call = client.calls[0]
    assert call["url"] == "http://gw/api/v1/messages"
    assert call["headers"]["x-api-key"] == "k"
    assert call["json"]["model"] == "claude-opus-4-8"
    assert call["json"]["tool_choice"] == {"type": "tool", "name": "record_triage"}
    assert "temperature" not in call["json"]  # Opus 4.8 拒绝 temperature


def test_http_error_translates_to_stage_error():
    with pytest.raises(StageError):
        _adapter(_FakeClient(_FakeResp({}, status=500))).classify(_req())


def test_network_error_translates_to_stage_error():
    with pytest.raises(StageError):
        _adapter(_FakeClient(exc=httpx.ConnectError("boom"))).classify(_req())


def test_missing_tool_use_translates_to_stage_error():
    payload = {"content": [{"type": "text", "text": "no tool call"}]}
    with pytest.raises(StageError):
        _adapter(_FakeClient(_FakeResp(payload))).classify(_req())


def test_invalid_enum_translates_to_stage_error():
    with pytest.raises(StageError):
        _adapter(_FakeClient(_FakeResp(_tool_use_payload(risk="CRITICAL")))).classify(_req())


def test_auth_headers_prefers_api_key_then_bearer_token(monkeypatch):
    monkeypatch.delenv("AUTODEV_LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AUTODEV_LLM_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok123")
    assert _auth_headers_from_env() == {"Authorization": "Bearer tok123"}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "keyabc")
    assert _auth_headers_from_env() == {"x-api-key": "keyabc"}

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert _auth_headers_from_env() == {}  # 缺失 → 空(生产打警告,调用时降级)


@pytest.mark.live
def test_live_smoke_real_gateway():
    if not os.environ.get("AUTODEV_LIVE"):
        pytest.skip("live 测试需 AUTODEV_LIVE=1 + 内网网关 + ANTHROPIC_AUTH_TOKEN")
    adapter = LlmTriageAdapter.from_env()
    sig = adapter.classify(_req("排查登录为什么偶发失败"))
    assert sig.intent is TriageIntent.CONSULTATION  # 咨询类应被真实模型识别
    assert isinstance(sig.confidence, float)
