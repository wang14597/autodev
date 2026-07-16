from tests.docs.docs_checks import (
    broken_links,
    extract_code_symbols,
    fabricated_symbols,
    internal_links,
    known_symbols,
    load_allowlist,
    parse_facts,
)


def test_extract_code_symbols_targets_codeish_tokens():
    md = "見 `WorkItem` 與 `handle_intake`，但 `venv`/`GitHub` 不算；`FooPort` 要抓。"
    got = extract_code_symbols(md)
    assert "WorkItem" in got and "handle_intake" in got and "FooPort" in got
    assert "venv" not in got  # 全小写无下划线, 非 codeish

def test_fabricated_symbols_flags_unknown(tmp_path):
    known = {"WorkItem", "handle_intake"}
    allow = {"GitHub"}
    md = "`WorkItem` `handle_intake` `FooPort` `GitHub`"
    assert fabricated_symbols(md, known, allow) == {"FooPort"}

def test_known_symbols_includes_class_def_and_enum_members(tmp_path):
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "m.py").write_text(
        "from enum import Enum, auto\n"
        "class FooPort:\n    pass\n"
        "def handle_bar():\n    pass\n"
        "class S(Enum):\n    ALPHA = auto()\n",
        encoding="utf-8",
    )
    names = known_symbols(tmp_path)
    assert {"FooPort", "handle_bar", "S", "ALPHA"} <= names

def test_internal_and_broken_links(tmp_path):
    (tmp_path / "exists.md").write_text("x", encoding="utf-8")
    md = tmp_path / "doc.md"
    text = "[a](exists.md) [b](missing.md) [c](https://x.com) [d](exists.md#frag)"
    md.write_text(text, encoding="utf-8")
    assert set(internal_links(md, text)) == {"exists.md", "missing.md"}
    assert broken_links(md, text) == ["missing.md"]

def test_parse_facts():
    assert parse_facts("<!-- fact:states -->12 and <!-- fact:ports -->`9`") == {"states": 12, "ports": 9}

def test_load_allowlist(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("# comment\nGitHub\n\nSQLite\n", encoding="utf-8")
    assert load_allowlist(p) == {"GitHub", "SQLite"}
