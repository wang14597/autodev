from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError

_NETWORK_HINTS = (
    "connection",
    "timed out",
    "could not resolve",
    "network",
    "gateway",
    "502",
    "503",
    "econnrefused",
    "rate limit",
    "overloaded",
)
_AUTH_HINTS = ("unauthorized", "authentication", "invalid api key", "forbidden", "401", "403")


def _classify(stderr: str) -> FailureKind:
    s = stderr.lower()
    if any(h in s for h in _NETWORK_HINTS):
        return FailureKind.TRANSIENT
    if any(h in s for h in _AUTH_HINTS):
        return FailureKind.FATAL
    return FailureKind.LOGIC


_TWO_HOURS = 7200


class ClaudeCodeRunner:
    """调 `claude` CLI 的共用基座：一次子进程调用，失败即上抛。

    **不做任何重试**。重试只保留引擎那一层（`RetryPolicy`）——它的计数落在
    `retry_ledger`、状态变更进 `history`，可见且持久化。此处曾有一层内部重试，
    与阶段级重试嵌套相乘，上限远超直觉且全程静默无痕。

    超时 2 小时：Claude Code CLI 的任务时长不可控，短超时会把接近完成的工作整个
    丢弃重来（实测评审阶段连续两次在 600 秒被杀，约 19 分钟模型工作作废）。
    """

    def __init__(
        self,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout: int = _TWO_HOURS,
    ) -> None:
        self._run = run
        self._timeout = timeout

    def run(self, prompt: str, cwd: Path, permission_mode: str = "plan") -> str:
        return self._invoke(prompt, cwd, permission_mode)

    def _invoke(self, prompt: str, cwd: Path, permission_mode: str) -> str:
        try:
            proc = self._run(
                ["claude", "-p", prompt, "--permission-mode", permission_mode, "--bare"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise StageError(FailureKind.TRANSIENT, "claude 超时") from e
        except FileNotFoundError as e:
            raise StageError(FailureKind.FATAL, "claude 不可用") from e
        if proc.returncode != 0:
            raise StageError(_classify(proc.stderr), f"claude 失败: {proc.stderr.strip()[:200]}")
        return proc.stdout.strip()
