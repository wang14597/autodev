"""真实 LLM 分诊适配器（子迭代 B）：直连 Anthropic Messages API 做结构化分诊。

铁律合规：LLM 只在本适配器（`adapters/`）；实现 `TriagePort` 协议；所有 HTTP/解析
异常在此边界翻译成领域 `StageError`（铁律 3），由 `handle_triage` 降级为挂起人审。

设计要点（依据 claude-api skill）：
- 结构化输出用**强制 `tool_use`**（单工具 record_triage + JSON schema + tool_choice），
  比裸解析散文 JSON 稳。
- 模型默认 `claude-opus-4-8`（Opus 4.8），可用 `AUTODEV_TRIAGE_MODEL` 覆盖。
- 不发 temperature（Opus 4.8 拒绝）；分类任务省略 thinking。
- 注入 `httpx.Client`（构造参数），生产用真 client、测试注入假 client 跑契约断言，无需网络。
- 鉴权:`ANTHROPIC_API_KEY`→`x-api-key`;`ANTHROPIC_AUTH_TOKEN`(内网网关)→`Authorization: Bearer`。
  base_url 取 `AUTODEV_LLM_BASE_URL` 或 `ANTHROPIC_BASE_URL`,默认官方。
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from autodev.domain.enums import FailureKind, RiskLevel, TaskType, TriageIntent
from autodev.domain.errors import StageError
from autodev.domain.value_objects import Requirement, TriageSignal

_DEFAULT_MODEL = "claude-opus-4-8"
_DEFAULT_BASE_URL = "https://api.anthropic.com"

_TRIAGE_TOOL: dict[str, Any] = {
    "name": "record_triage",
    "description": "记录对研发需求的分诊结论。",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "level": {
                "type": "string",
                "enum": ["SMALL_CHANGE", "MEDIUM_FEATURE", "COMPLEX_FEATURE"],
                "description": "任务规模。",
            },
            "risk": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH"],
                "description": "改动风险(触碰安全/凭证/破坏性操作→HIGH)。",
            },
            "intent": {
                "type": "string",
                "enum": ["ACTIONABLE", "CONSULTATION"],
                "description": "需落地代码改动=ACTIONABLE;查询/咨询/仅需求收集=CONSULTATION。",
            },
            "confidence": {
                "type": "number",
                "description": "对本次分诊的把握度,0.0-1.0。",
            },
            "signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "支撑判断的可解释依据(简短短语)。",
            },
        },
        "required": ["level", "risk", "intent", "confidence", "signals"],
        "additionalProperties": False,
    },
}

_SYSTEM = (
    "你是 AI 研发工作流的分诊器。基于需求文本判断任务规模、改动风险、意图与把握度,"
    "并必须调用 record_triage 工具记录结论。意图为查询/咨询/仅需求收集时用 CONSULTATION,"
    "需要落地代码改动时用 ACTIONABLE。触碰删除/迁移/安全/凭证/权限等用 HIGH 风险。"
)


def _auth_headers_from_env() -> dict[str, str]:
    """从环境变量解析鉴权头。API key → x-api-key;auth token(内网网关)→ Authorization: Bearer。

    缺失时返回空 dict —— 生产组合根据此打启动警告;每次分诊调用将因 401 → StageError →
    降级为挂起人审(不 fail-fast、不阻断平台)。
    """
    api_key = os.environ.get("AUTODEV_LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return {"x-api-key": api_key}
    token = os.environ.get("AUTODEV_LLM_AUTH_TOKEN") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


class _HttpClient(Protocol):
    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> Any: ...


class LlmTriageAdapter:
    """`TriagePort` 的真实实现:直连 Messages API,强制 tool_use 结构化输出。"""

    def __init__(
        self, client: _HttpClient, model: str, base_url: str, auth_headers: dict[str, str]
    ) -> None:
        self._client = client
        self._model = model
        self._auth_headers = auth_headers
        self._url = base_url.rstrip("/") + "/v1/messages"

    @classmethod
    def from_env(cls) -> LlmTriageAdapter:
        import httpx

        base_url = (
            os.environ.get("AUTODEV_LLM_BASE_URL")
            or os.environ.get("ANTHROPIC_BASE_URL")
            or _DEFAULT_BASE_URL
        )
        model = os.environ.get("AUTODEV_TRIAGE_MODEL") or _DEFAULT_MODEL
        return cls(httpx.Client(timeout=30.0), model, base_url, _auth_headers_from_env())

    def classify(self, requirement: Requirement) -> TriageSignal:
        body = {
            "model": self._model,
            "max_tokens": 1024,
            "system": _SYSTEM,
            "tools": [_TRIAGE_TOOL],
            "tool_choice": {"type": "tool", "name": "record_triage"},
            "messages": [
                {
                    "role": "user",
                    "content": f"需求:\n{requirement.goal}\n\n原文:\n{requirement.raw_text}",
                }
            ],
        }
        headers = {
            **self._auth_headers,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # 网络/超时/非 2xx → 基础设施失败(TRANSIENT);由 handle_triage 降级挂起人审。
        try:
            resp = self._client.post(self._url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        except StageError:
            raise
        except Exception as e:  # noqa: BLE001 ACL 边界:一切外部异常翻译成领域失败
            raise StageError(FailureKind.TRANSIENT, f"triage LLM 调用失败: {e}") from e

        return self._parse(data)

    @staticmethod
    def _parse(data: dict[str, Any]) -> TriageSignal:
        # 从响应内容里取 record_triage 工具调用的结构化入参。
        try:
            tool_input: dict[str, Any] | None = None
            for block in data.get("content", []):
                if block.get("type") == "tool_use" and block.get("name") == "record_triage":
                    tool_input = block.get("input")
                    break
            if tool_input is None:
                raise ValueError("响应缺少 record_triage tool_use 块")
            return TriageSignal(
                level=TaskType[tool_input["level"]],
                confidence=float(tool_input["confidence"]),
                risk=RiskLevel[tool_input["risk"]],
                intent=TriageIntent[tool_input["intent"]],
                signals=tuple(tool_input.get("signals", [])),
            )
        except StageError:
            raise
        except (KeyError, ValueError, TypeError) as e:
            # 非法枚举/缺字段/结构错误 → 领域失败(FATAL);同样被 handle_triage 降级。
            raise StageError(FailureKind.FATAL, f"triage LLM 响应解析失败: {e}") from e
