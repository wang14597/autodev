import subprocess

import pytest

from autodev.adapters.claude_runner import ClaudeCodeRunner, _classify
from autodev.domain.enums import FailureKind
from autodev.domain.errors import StageError


def test_classify():
    assert _classify("Error: overloaded_error 503") is FailureKind.TRANSIENT
    assert _classify("invalid api key / 401 unauthorized") is FailureKind.FATAL
    assert _classify("some other error") is FailureKind.LOGIC


def test_run_success_returns_stdout(tmp_path):
    def fake(*a, **k):
        return subprocess.CompletedProcess(a, 0, stdout="RESULT\n", stderr="")

    assert ClaudeCodeRunner(run=fake).run("p", tmp_path) == "RESULT"


def test_run_timeout_transient(tmp_path):
    def fake(*a, **k):
        raise subprocess.TimeoutExpired("claude", 1)

    with pytest.raises(StageError) as ei:
        ClaudeCodeRunner(run=fake, max_retries=0).run("p", tmp_path)
    assert ei.value.failure_kind is FailureKind.TRANSIENT


def test_run_missing_binary_fatal(tmp_path):
    def fake(*a, **k):
        raise FileNotFoundError("claude")

    with pytest.raises(StageError) as ei:
        ClaudeCodeRunner(run=fake).run("p", tmp_path)
    assert ei.value.failure_kind is FailureKind.FATAL


def test_run_retries_transient_then_succeeds(tmp_path):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            return subprocess.CompletedProcess(a, 1, stdout="", stderr="connection timed out")
        return subprocess.CompletedProcess(a, 0, stdout="OK", stderr="")

    out = ClaudeCodeRunner(run=fake, max_retries=3, sleep=lambda s: None).run("p", tmp_path)
    assert out == "OK" and calls["n"] == 3


def test_run_invokes_expected_args(tmp_path):
    seen = {}

    def fake(cmd, **k):
        seen["cmd"] = cmd
        seen["cwd"] = k.get("cwd")
        seen["timeout"] = k.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, stdout="x", stderr="")

    ClaudeCodeRunner(run=fake, timeout=600).run("PROMPT", tmp_path, permission_mode="plan")
    assert seen["cmd"] == ["claude", "-p", "PROMPT", "--permission-mode", "plan", "--bare"]
    assert seen["cwd"] == str(tmp_path) and seen["timeout"] == 600
