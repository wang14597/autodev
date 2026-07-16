from __future__ import annotations

import subprocess
import sys

_PROMPT = (
    "你是文档一致性顾问。请自行只读调查本仓库: 用 git 查看本次将要 push 的改动"
    "(对比 origin/main), 并阅读候选文档(README、ROADMAP、CHANGELOG、"
    "docs/architecture/diagrams.md、docs/adr)。判断哪些文档可能因这些改动而过时, "
    "列出简短清单(文件名 + 一句原因); 若无则回复'无'。"
    "这是只读建议——不要修改/创建/删除任何文件, 也不要提交。"
)


def build_prompt() -> str:
    return _PROMPT


def advise(runner) -> str:
    try:
        return runner(build_prompt())
    except Exception as e:  # noqa: BLE001 顾问永不阻塞
        return f"文档顾问跳过: {e}(非阻塞)"


def _claude_runner(prompt: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", prompt, "--permission-mode", "plan", "--bare"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "claude 非零退出").strip()[:200])
    return proc.stdout.strip()


def main() -> int:
    print("── 文档一致性顾问(本地, 非阻塞) ──")
    try:
        print(advise(_claude_runner))
    except Exception as e:  # noqa: BLE001 绝不阻塞 push
        print(f"文档顾问跳过(顶层兜底): {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
