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
        ClaudeCodeRunner(run=fake).run("p", tmp_path)
    assert ei.value.failure_kind is FailureKind.TRANSIENT


def test_run_missing_binary_fatal(tmp_path):
    def fake(*a, **k):
        raise FileNotFoundError("claude")

    with pytest.raises(StageError) as ei:
        ClaudeCodeRunner(run=fake).run("p", tmp_path)
    assert ei.value.failure_kind is FailureKind.FATAL


def test_run_does_not_retry_transient_failures(tmp_path):
    """瞬时失败只调一次就上抛——runner 内部不再重试。

    判别性：旧实现对 TRANSIENT 会重试到 max_retries，calls["n"] 会 > 1。
    去掉这层的理由见 CHANGELOG：它与引擎 RetryPolicy 的阶段级重试嵌套相乘，
    上限远超直觉，且整个过程静默无痕。重试现在只保留引擎那一层（计数落在
    retry_ledger、状态变更进 history，可见且持久化）。
    """
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        return subprocess.CompletedProcess(a, 1, stdout="", stderr="connection timed out")

    with pytest.raises(StageError) as ei:
        ClaudeCodeRunner(run=fake).run("p", tmp_path)
    assert ei.value.failure_kind is FailureKind.TRANSIENT
    assert calls["n"] == 1


def test_default_timeout_is_two_hours(tmp_path):
    """默认超时 2 小时：Claude Code CLI 的任务时长不可控，短超时会把接近完成的
    工作整个丢弃重来（实测评审阶段连续两次在 600 秒被杀，约 19 分钟模型工作作废）。
    """
    seen = {}

    def fake(cmd, **k):
        seen["timeout"] = k.get("timeout")
        return subprocess.CompletedProcess(cmd, 0, stdout="x", stderr="")

    ClaudeCodeRunner(run=fake).run("p", tmp_path)
    assert seen["timeout"] == 7200


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
