from __future__ import annotations

import os
import subprocess
import sys

_DOCS = "README/ROADMAP/CHANGELOG/docs/architecture/diagrams.md/docs/adr"
_MAX = 60_000


def build_prompt(diff_text: str) -> str:
    return (
        "你是文档一致性顾问。下面是本次改动的代码 diff。请判断哪些文档("
        + _DOCS
        + ")可能因此过时, 列成简短清单; 若无则回复'无'。这是只读建议, 不要修改任何文件。\n\n"
        "DIFF:\n" + diff_text
    )


def gather_src_diff(base: str) -> str:
    try:
        out = subprocess.run(
            ["git", "diff", f"{base}...HEAD", "--", "src/**"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
    except Exception:  # noqa: BLE001 顾问永不阻塞: 任何 git 失败都当作无 diff
        return ""
    return out[:_MAX]


def advise(runner, diff_text: str) -> str:
    if not diff_text.strip():
        return "无 src 改动, 文档顾问跳过。"
    try:
        return runner(build_prompt(diff_text))
    except Exception as e:  # noqa: BLE001 顾问永不阻塞
        return f"文档顾问跳过: {e}(非阻塞)"


def _claude_runner(prompt: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", "--permission-mode", "plan"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "claude 非零退出").strip()[:200])
    return proc.stdout.strip()


def main() -> int:
    try:
        base = os.environ.get("DOC_ADVISE_BASE", "origin/main")
        diff_text = gather_src_diff(base)
        print("── 文档一致性顾问(本地, 非阻塞) ──")
        print(advise(_claude_runner, diff_text))
    except Exception as e:  # noqa: BLE001 绝不阻塞 push
        print(f"文档顾问跳过(顶层兜底): {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
