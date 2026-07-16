from scripts.check_doc_impact import evaluate

RULES = [
    {"paths": ["src/autodev/domain/ports.py"], "docs": ["README.md", "CHANGELOG.md"]},
    {"paths": ["src/autodev/**"], "docs": ["CHANGELOG.md"]},
]


def test_violation_when_code_changed_without_docs():
    changed = ["src/autodev/domain/ports.py"]
    v = evaluate(changed, RULES, set(changed))
    # ports.py 命中两条规则; 都缺文档
    assert any("README.md" in x for x in v)
    assert any("CHANGELOG.md" in x for x in v)


def test_no_violation_when_docs_updated():
    changed = ["src/autodev/domain/ports.py", "README.md", "CHANGELOG.md"]
    assert evaluate(changed, RULES, set(changed)) == []


def test_glob_double_star_matches_nested():
    changed = ["src/autodev/application/engine.py"]
    v = evaluate(changed, RULES, set(changed))
    assert any("CHANGELOG.md" in x for x in v)  # 命中 src/autodev/**


def test_skip_escape_hatch():
    changed = ["src/autodev/domain/ports.py"]
    assert evaluate(changed, RULES, set(changed), skip=True) == []


def test_unrelated_change_no_violation():
    changed = ["docs/foo.md"]
    assert evaluate(changed, RULES, set(changed)) == []
