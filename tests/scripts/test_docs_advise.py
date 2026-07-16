from scripts.docs_advise import advise, build_prompt


def test_build_prompt_names_docs_and_is_read_only():
    p = build_prompt()
    assert "README" in p and "CHANGELOG" in p and "docs/adr" in p
    assert "不要修改" in p or "只读" in p


def test_advise_runs_runner_and_returns_output():
    assert advise(lambda prompt: "疑似过时: CHANGELOG") == "疑似过时: CHANGELOG"


def test_advise_passes_prompt_to_runner():
    seen = {}
    advise(lambda prompt: seen.setdefault("p", prompt) or "ok")
    assert "README" in seen["p"]  # 传给 runner 的是 build_prompt()


def test_advise_degrades_when_runner_raises():
    def boom(prompt):
        raise RuntimeError("claude 不可用")

    out = advise(boom)
    assert "跳过" in out and "claude 不可用" in out


def test_main_always_returns_zero(monkeypatch):
    import scripts.docs_advise as m

    monkeypatch.setattr(
        m, "_claude_runner", lambda prompt: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert m.main() == 0
