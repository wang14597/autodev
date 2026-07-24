from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.docs.docs_checks import (
    broken_links,
    fabricated_symbols,
    known_symbols,
    load_allowlist,
    parse_facts,
)

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "autodev"
ALLOWLIST = REPO / "docs" / ".doc-allowlist.txt"


def _tracked_markdown() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=REPO, capture_output=True, text=True, check=True
    )
    return [REPO / line for line in out.stdout.splitlines() if line]


def _code_truth() -> dict[str, int]:
    sys.path.insert(0, str(REPO / "src"))
    from autodev.domain import artifacts, enums, events, ports
    from autodev.domain.events import DomainEvent

    n_states = len(list(enums.WorkflowState))
    n_artifacts = sum(
        1
        for v in vars(artifacts).values()
        if isinstance(v, type) and v.__name__.endswith("Artifact")
    )
    n_ports = sum(
        1
        for v in vars(ports).values()
        if isinstance(v, type)
        and (
            v.__name__.endswith("Port")
            or v.__name__ in {"WorkItemRepository", "ProjectRepository", "EventPublisher"}
        )
    )
    n_events = sum(
        1
        for v in vars(events).values()
        if isinstance(v, type) and issubclass(v, DomainEvent) and v is not DomainEvent
    )
    return {
        "workflow_states": n_states,
        "artifacts": n_artifacts,
        "ports": n_ports,
        "events": n_events,
    }


def test_no_fabricated_code_symbols_in_docs():
    # 已知符号取自 src/autodev 与 tests(含 tests/fakes.py 的假适配器类)——
    # 测试专用的真实符号(FakeWorkspace 等)因此被识别为真, 无需塞进白名单,
    # 且将来被重命名时文档引用仍会被抓到。
    known = known_symbols(SRC) | known_symbols(REPO / "tests")
    allow = load_allowlist(ALLOWLIST)
    problems = {}
    for md in _tracked_markdown():
        fab = fabricated_symbols(md.read_text(encoding="utf-8"), known, allow)
        if fab:
            problems[str(md.relative_to(REPO))] = sorted(fab)
    assert not problems, f"文档出现代码中不存在的符号(伪造/漂移): {problems}"


def test_no_broken_internal_links():
    problems = {}
    for md in _tracked_markdown():
        bad = broken_links(md, md.read_text(encoding="utf-8"))
        if bad:
            problems[str(md.relative_to(REPO))] = bad
    assert not problems, f"文档存在坏内链: {problems}"


def test_doc_fact_counts_match_code():
    truth = _code_truth()
    mismatches = []
    for md in _tracked_markdown():
        for key, val in parse_facts(md.read_text(encoding="utf-8")).items():
            if key in truth and val != truth[key]:
                mismatches.append(f"{md.relative_to(REPO)}: {key}={val} 但代码={truth[key]}")
    assert not mismatches, f"文档计数与代码不符: {mismatches}"


def test_at_least_one_fact_marker_exists():
    # 防止"标记全被删掉导致计数检查空转"
    total = sum(len(parse_facts(md.read_text(encoding="utf-8"))) for md in _tracked_markdown())
    assert total > 0, "未发现任何 fact 标记, 计数检查形同虚设"
