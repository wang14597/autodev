from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from pathlib import Path


def _match(path: str, pattern: str) -> bool:
    # 支持 ** 递归: 转成 fnmatch 语义
    if pattern.endswith("/**"):
        return path == pattern[:-3] or path.startswith(pattern[:-2])
    return fnmatch.fnmatch(path, pattern)


def evaluate(
    changed: list[str],
    rules: list[dict],
    changed_set: set[str],
    skip: bool = False,
) -> list[str]:
    if skip:
        return []
    violations: list[str] = []
    for rule in rules:
        hit = [c for c in changed for p in rule["paths"] if _match(c, p)]
        if not hit:
            continue
        missing = [d for d in rule["docs"] if d not in changed_set]
        if missing:
            violations.append(
                f"改动 {sorted(set(hit))} 命中规则 {rule['paths']}, 但未更新文档: {missing}"
            )
    return violations


def load_rules(path: Path) -> list[dict]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("rules", [])


def _changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [x for x in out.stdout.splitlines() if x]


def main() -> int:
    base = os.environ.get("DOC_IMPACT_BASE", "origin/main")
    skip = os.environ.get("DOCS_IMPACT_SKIP") == "1"
    rules = load_rules(Path("docs/doc-ownership.yml"))
    changed = _changed_files(base)
    violations = evaluate(changed, rules, set(changed), skip=skip)
    if violations:
        print("文档影响检查失败:")
        for v in violations:
            print(" - " + v)
        print(
            "如确实无需文档: 给 PR 打标签 `docs:none-needed` 或提交尾注 "
            "`Docs-Impact: none — <理由>`"
        )
        return 1
    print("文档影响检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
