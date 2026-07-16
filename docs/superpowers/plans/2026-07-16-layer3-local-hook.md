# 第 3 层改为本地 pre-push 顾问 Implementation Plan

> **For agentic workers:** subagent-driven-development 逐任务执行 + 评审。含 Python 走 TDD。

**Goal:** 因内网 key 无法在 GitHub 云 runner 使用，把文档一致性"第 3 层 AI 顾问"从云端 `docs-advisor.yml` 改为**本地 pre-push 钩子**：push 前在开发者本机（VPN 已连、本地 Claude Code 可用）跑一次，打印"疑似过时文档"，始终非阻塞、环境不可用则优雅跳过。撤掉云上的第 3 层 workflow。

**Architecture:** 顾问逻辑 = 纯函数（组 prompt）+ 薄 I/O（取 git diff、调 `claude -p`、打印）。经 pre-commit 的 `pre-push` stage 触发（版本化、可 `pre-commit install --hook-type pre-push`）。第 1、2 层（GitHub Actions，无 LLM）不变。

**Tech Stack:** Python(subprocess/pathlib)、pytest、pre-commit、本地 `claude` CLI。

## Global Constraints
- 顾问**永不阻塞**：任何情况下退出码 0（无 src 改动 / claude 不可用 / 网络不通 / 超时 → 打印说明并 exit 0）。
- 不改 `src/autodev/**` 运行时行为；第 1、2 层配置不动。
- 撤掉 `.github/workflows/docs-advisor.yml`（`.github/workflows/**` 变更按我们自己的 doc-ownership 规则需 CHANGELOG 条目——本批次会加）。
- 门禁保持绿：`ruff check . && ruff format --check . && mypy src && pytest -q`。
- Conventional Commits；提交人 `AutoDev <autodev@local>`，body 末附 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。

## File Structure
```
scripts/docs_advise.py             # 本地顾问: 取 src diff -> prompt -> claude -p -> 打印(非阻塞)
tests/scripts/test_docs_advise.py  # 纯函数单测(prompt 组装 + 优雅降级)
.pre-commit-config.yaml            # 追加 pre-push stage 的 docs-advise 钩子
(删除) .github/workflows/docs-advisor.yml
CONTRIBUTING.md / README.md        # 记录 `pre-commit install --hook-type pre-push` 一次性安装
docs/superpowers/specs/2026-07-16-doc-consistency-ci-design.md  # 第3层小节改写为本地钩子
CHANGELOG.md / ROADMAP.md          # 记录第3层从云改本地
```

---

### Task 1: 本地顾问脚本 + 单测 + pre-push 钩子

**Files:** Create `scripts/docs_advise.py`, `tests/scripts/test_docs_advise.py`; Modify `.pre-commit-config.yaml`

**Interfaces:**
- `build_prompt(diff_text: str) -> str` — 组装给模型的中文 prompt：给定 src diff，让其判断哪些文档(README/ROADMAP/CHANGELOG/docs/architecture/diagrams.md/docs/adr)可能过时，列简短清单，无则回"无"；明确"只读、不要改文件"。
- `gather_src_diff(base: str) -> str` — `git diff {base}...HEAD -- 'src/**'`（截断到 ~60k 字符）。
- `advise(runner, diff_text) -> str` — 若 diff 空返回提示串；否则 `runner(build_prompt(diff))`；`runner` 抛异常时返回"顾问跳过: <原因>(非阻塞)"。（`runner` 注入以便单测，无需真调 claude。）
- `main() -> int` — 取 `DOC_ADVISE_BASE`(默认 `origin/main`)；`advise(...)` 用真实 `_claude_runner`；打印结果；**永远 return 0**。

- [ ] **Step 1: 写失败测试**

```python
# tests/scripts/test_docs_advise.py
from scripts.docs_advise import build_prompt, advise

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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/scripts/test_docs_advise.py -q` → FAIL。

- [ ] **Step 3: 实现**

```python
# scripts/docs_advise.py
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
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        out = ""
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
        input=prompt, capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "claude 非零退出").strip()[:200])
    return proc.stdout.strip()


def main() -> int:
    base = os.environ.get("DOC_ADVISE_BASE", "origin/main")
    diff_text = gather_src_diff(base)
    print("── 文档一致性顾问(本地, 非阻塞) ──")
    print(advise(_claude_runner, diff_text))
    return 0  # 永不阻塞 push


if __name__ == "__main__":
    sys.exit(main())
```
Create `tests/scripts/__init__.py` if not already present (DC5 已建, 复用)。

- [ ] **Step 4: 跑测试确认通过**

Run: `. venv/bin/activate && pytest tests/scripts/test_docs_advise.py -q` → `4 passed`。全套 `pytest -q` 绿。

- [ ] **Step 5: 加 pre-push 钩子**

在 `.pre-commit-config.yaml` 追加一个 local repo 钩子（`pre-push` stage、`always_run`、非阻塞靠脚本自身 exit 0）：
```yaml
  - repo: local
    hooks:
      - id: docs-advise
        name: 文档一致性顾问(本地, 非阻塞)
        entry: python scripts/docs_advise.py
        language: system
        stages: [pre-push]
        always_run: true
        pass_filenames: false
        verbose: true
```

- [ ] **Step 6: 校验 + Commit**

Run: `python -c "import yaml; yaml.safe_load(open('.pre-commit-config.yaml')); print('ok')"`；`ruff check scripts tests/scripts`。
```bash
git add scripts/docs_advise.py tests/scripts/test_docs_advise.py .pre-commit-config.yaml
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "feat(docs): 第3层改为本地 pre-push 文档顾问(非阻塞)"
```

---

### Task 2: 撤掉云上第 3 层 + 更新文档

**Files:** Delete `.github/workflows/docs-advisor.yml`; Modify `docs/superpowers/specs/2026-07-16-doc-consistency-ci-design.md`, `README.md`, `ROADMAP.md`, `CHANGELOG.md`, `CONTRIBUTING.md`

**Interfaces:** Produces docs/config aligned to "第3层=本地钩子"。

- [ ] **Step 1: 删云 workflow**

Run: `git rm .github/workflows/docs-advisor.yml`

- [ ] **Step 2: 改设计文档第 3 层**

在 `docs/superpowers/specs/2026-07-16-doc-consistency-ci-design.md` 的"第 3 层"小节，改写为：因内网 key 不能在 GitHub 云 runner 使用，第 3 层实现为**本地 `pre-push` 钩子**（`scripts/docs_advise.py`，经 pre-commit pre-push stage），在开发者本机(VPN 已连、本地 Claude Code)运行；非阻塞、环境不可用则跳过。§5 编排里移除 `docs-advisor.yml` 的描述。（保留"绝不硬阻塞、缺则跳过"的原则。）

- [ ] **Step 3: 更新 CONTRIBUTING/README 安装说明**

`CONTRIBUTING.md` 与 `README.md`：加一句一次性安装——`pre-commit install --hook-type pre-push`，说明 push 前会本地跑文档顾问(非阻塞)；也可手动 `python scripts/docs_advise.py`。

- [ ] **Step 4: CHANGELOG / ROADMAP**

- `CHANGELOG.md` `[Unreleased] ### Changed`：加一条——第 3 层 AI 文档顾问从 GitHub Actions 工作流改为本地 pre-push 钩子(内网 key 约束)；移除 `.github/workflows/docs-advisor.yml`。
- `ROADMAP.md`：若"横向/可观测"或基线处提到第 3 层为 CI 顾问，改为本地钩子表述。

- [ ] **Step 5: 校验 + Commit**

Run: `. venv/bin/activate && pytest tests/docs/ -q`（内链/符号检查全绿；确认删文件后没有文档还把 `docs-advisor.yml` 当现存文件引用——若有则改）；`pytest -q` 全绿；`grep -rn 'docs-advisor' --include='*.md' . | grep -v superpowers` 只应出现在"已移除/历史"语境。
```bash
git add -A .github/ docs/ README.md ROADMAP.md CHANGELOG.md CONTRIBUTING.md
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "docs: 撤掉云第3层, 文档改为本地钩子表述 + CHANGELOG"
```

---

## Self-Review
- 覆盖：本地顾问脚本(Task1) + 钩子接入(Task1) + 撤云 workflow + 全文档对齐(Task2)。
- 非阻塞保证：`main()` 恒返回 0；`advise` 对空 diff 与 runner 异常都优雅处理，有单测锁定。
- 一致性：删 `docs-advisor.yml` 后设计/README/ROADMAP/CHANGELOG 均更新；`.github/workflows/**` 变更按自有规则记 CHANGELOG。
- 占位扫描：无 TBD；每 code step 含完整代码/命令。
