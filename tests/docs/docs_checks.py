from __future__ import annotations

import ast
import re
from pathlib import Path

_BACKTICK = re.compile(r"`([^`]+)`")
_CAMEL = re.compile(r"^[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*$")
_HANDLE = re.compile(r"^handle_[a-z_]+$")
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_FACT = re.compile(r"<!--\s*fact:(\w+)\s*-->\s*`?(\d+)`?")
_FENCE = re.compile(r"```.*?```", re.S)


def strip_code_fences(md: str) -> str:
    """Remove fenced code blocks (```...``` incl. ```lang) from markdown text.

    Example markdown/code inside fenced blocks (e.g. `[a](missing.md)` used to
    illustrate the link checker itself) must not be scanned by the link or
    symbol checks below, only prose and inline `` `code` `` spans should be.
    """
    return _FENCE.sub("", md)


def _is_codeish(token: str) -> bool:
    return bool(_CAMEL.match(token) or _HANDLE.match(token))


def known_symbols(src_root: Path) -> set[str]:
    names: set[str] = set()
    for py in src_root.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
    return names


def extract_code_symbols(md_text: str) -> set[str]:
    out: set[str] = set()
    for m in _BACKTICK.finditer(strip_code_fences(md_text)):
        token = m.group(1).strip()
        if _is_codeish(token):
            out.add(token)
    return out


def fabricated_symbols(md_text: str, known: set[str], allow: set[str]) -> set[str]:
    return {t for t in extract_code_symbols(md_text) if t not in known and t not in allow}


def internal_links(md_path: Path, md_text: str) -> list[str]:
    out: list[str] = []
    for m in _LINK.finditer(strip_code_fences(md_text)):
        target = m.group(1).split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        out.append(target)
    return out


def broken_links(md_path: Path, md_text: str) -> list[str]:
    base = md_path.parent
    return [t for t in internal_links(md_path, md_text) if not (base / t).exists()]


def parse_facts(md_text: str) -> dict[str, int]:
    return {m.group(1): int(m.group(2)) for m in _FACT.finditer(md_text)}


def load_allowlist(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.add(s)
    return out
