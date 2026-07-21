from __future__ import annotations

import subprocess
import time
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


class ClaudeCodeRunner:
    def __init__(
        self,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout: int = 600,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._run = run
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep = sleep

    def run(self, prompt: str, cwd: Path, permission_mode: str = "plan") -> str:
        attempt = 0
        while True:
            try:
                return self._invoke(prompt, cwd, permission_mode)
            except StageError as e:
                if e.failure_kind is FailureKind.TRANSIENT and attempt < self._max_retries:
                    attempt += 1
                    self._sleep(min(2**attempt, 30))
                    continue
                raise

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
