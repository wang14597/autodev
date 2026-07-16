from scripts.docs_advise import advise, build_prompt


def test_build_prompt_contains_diff_and_instructions():
    p = build_prompt("--- a/src/x.py\n+++ b/src/x.py\n+def foo(): ...")
    assert "def foo" in p
    assert "README" in p and "CHANGELOG" in p
    assert ("不要" in p) or ("只读" in p)  # 只读约束


def test_advise_empty_diff_short_circuits():
    called = []
    out = advise(lambda prompt: called.append(1) or "X", "")
    assert "无 src 改动" in out or "no src" in out.lower()
    assert not called  # diff 空时不调用模型


def test_advise_runs_runner_on_nonempty_diff():
    out = advise(lambda prompt: "疑似过时: CHANGELOG", "some diff")
    assert "CHANGELOG" in out


def test_advise_degrades_gracefully_when_runner_raises():
    def boom(prompt):
        raise RuntimeError("claude 不可用")

    out = advise(boom, "some diff")
    assert "跳过" in out and "claude 不可用" in out
