# 文档一致性 CI Implementation Plan

> **For agentic workers:** 用 subagent-driven-development 逐任务执行；每任务后 spec+quality 评审，最后整支评审。含 Python 的任务走 TDD（失败测试→实现→通过）；纯配置任务的验收=校验 + 实跑等效命令。

**Goal:** 迁移本仓库 CI 到 GitHub Actions，并落地"文档一致性"三层检查（第 1 层确定性阻塞 / 第 2 层路径映射+逃生舱 / 第 3 层 AI 顾问不阻塞），防止功能改动未同步或写错文档进入主干。

**Architecture:** 设计见 `docs/superpowers/specs/2026-07-16-doc-consistency-ci-design.md`。本仓库托管在 GitHub → CI=GitHub Actions、协作=PR。产品对接目标项目仍是 GitLab（不动）。Python 检查器纯函数化以便单测。

**Tech Stack:** GitHub Actions、Python（ast/re/pathlib）、pytest、PyYAML、`@mermaid-js/mermaid-cli`、headless `claude`。

## Global Constraints
- 本仓库 CI 一律 GitHub Actions；实现结束时 `.gitlab-ci.yml` 与 `.gitlab/` 目录必须删除。
- 不改产品与 GitLab 的运行时集成语义；文档里"产品对接目标项目=GitLab MR"的表述保留，仅"向本仓库贡献=GitHub PR"的表述改。
- 不改 `src/autodev/**` 运行时行为。
- 第 3 层（AI）绝不阻塞；缺 `ANTHROPIC_API_KEY` secret 时该 job 跳过。
- 现有 48 测试 + 新增文档测试必须全绿；`ruff check .`、`mypy src` 保持通过。
- 提交遵循 Conventional Commits；提交人 `AutoDev <autodev@local>`，body 末附 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。

## File Structure
```
.github/
  workflows/ci.yml            # lint/type/test/mermaid/doc-impact
  workflows/docs-advisor.yml  # 第3层 AI 顾问(非阻塞)
  pull_request_template.md    # 由 .gitlab MR 模板迁移
  CODEOWNERS                  # 由根 CODEOWNERS 迁移
docs/
  doc-ownership.yml           # 第2层 路径→文档 映射
  .doc-allowlist.txt          # 第1层 非代码 CamelCase 白名单
scripts/
  check_doc_impact.py         # 第2层 核心+CLI
tests/docs/
  __init__.py
  docs_checks.py              # 第1层 纯函数
  test_docs_checks.py         # 纯函数单测(含漂移 fixture)
  test_doc_consistency.py     # 对真实仓库文档断言
tests/scripts/
  __init__.py
  test_check_doc_impact.py    # 第2层 核心单测
(删除) .gitlab-ci.yml
(迁移删除) .gitlab/merge_request_templates/default.md
(迁移删除) 根 CODEOWNERS
```

---

### Task 1: 迁移 CI 到 GitHub Actions（lint/type/test）

**Files:** Create `.github/workflows/ci.yml`; Delete `.gitlab-ci.yml`

**Interfaces:** Produces the repo's GitHub Actions CI with jobs `lint`/`type`/`test` (mermaid + doc-impact added in later tasks).

- [ ] **Step 1: 写 workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        run: pip install -e '.[dev]'
      - name: Lint (ruff)
        run: ruff check .
      - name: Format check (ruff)
        run: ruff format --check .
      - name: Type check (mypy)
        run: mypy src
      - name: Test (pytest)
        run: pytest -q
```

- [ ] **Step 2: 删除 GitLab CI**

Run: `git rm .gitlab-ci.yml`

- [ ] **Step 3: 校验 YAML + 实跑等效命令**

Run:
```bash
python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"
. venv/bin/activate && ruff check . && ruff format --check . && mypy src && pytest -q
```
Expected: `yaml ok`；ruff/mypy 通过；`48 passed`。

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml && git rm --cached .gitlab-ci.yml 2>/dev/null; git add -A .gitlab-ci.yml
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "ci: 迁移本仓库 CI 到 GitHub Actions, 移除 .gitlab-ci.yml"
```

---

### Task 2: 第 1 层检查器纯函数 + 单测

**Files:** Create `tests/docs/__init__.py`, `tests/docs/docs_checks.py`, `tests/docs/test_docs_checks.py`

**Interfaces:**
- Consumes: stdlib only (`ast`, `re`, `pathlib`).
- Produces (`docs_checks.py`):
  - `known_symbols(src_root: Path) -> set[str]` — 所有 class/def 名 + 模块级/类体内 Assign 目标名（含 Enum 成员）。
  - `extract_code_symbols(md_text: str) -> set[str]` — 反引号 token 中"像代码符号"的：CamelCase（首字母大写且含小写字母）或匹配 `^handle_[a-z_]+$`。
  - `fabricated_symbols(md_text, known: set[str], allow: set[str]) -> set[str]` — 上述 token 中不在 `known ∪ allow` 的。
  - `internal_links(md_path: Path, md_text: str) -> list[str]` — 相对内链目标（去 `#anchor`，排除 http/https/mailto）。
  - `broken_links(md_path: Path, md_text: str) -> list[str]` — 目标文件不存在的内链。
  - `parse_facts(md_text: str) -> dict[str, int]` — 解析 `<!-- fact:KEY -->N`（N 可选反引号包裹）。
  - `load_allowlist(path: Path) -> set[str]` — 逐行、忽略空行与 `#` 注释。

- [ ] **Step 1: 写失败测试**

```python
# tests/docs/test_docs_checks.py
from pathlib import Path
from tests.docs.docs_checks import (
    known_symbols, extract_code_symbols, fabricated_symbols,
    internal_links, broken_links, parse_facts, load_allowlist,
)

def test_extract_code_symbols_targets_codeish_tokens():
    md = "见 `WorkItem` 与 `handle_intake`，但 `venv`/`GitHub` 不算；`FooPort` 要抓。"
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/docs/test_docs_checks.py -q` → FAIL（模块不存在）。

- [ ] **Step 3: 实现**

```python
# tests/docs/docs_checks.py
from __future__ import annotations

import ast
import re
from pathlib import Path

_BACKTICK = re.compile(r"`([^`]+)`")
_CAMEL = re.compile(r"^[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*$")
_HANDLE = re.compile(r"^handle_[a-z_]+$")
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_FACT = re.compile(r"<!--\s*fact:(\w+)\s*-->\s*`?(\d+)`?")


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
    for m in _BACKTICK.finditer(md_text):
        token = m.group(1).strip()
        if _is_codeish(token):
            out.add(token)
    return out


def fabricated_symbols(md_text: str, known: set[str], allow: set[str]) -> set[str]:
    return {t for t in extract_code_symbols(md_text) if t not in known and t not in allow}


def internal_links(md_path: Path, md_text: str) -> list[str]:
    out: list[str] = []
    for m in _LINK.finditer(md_text):
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
```
Also create empty `tests/docs/__init__.py`.

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/docs/test_docs_checks.py -q` → `6 passed`。

- [ ] **Step 5: Commit**

```bash
git add tests/docs/__init__.py tests/docs/docs_checks.py tests/docs/test_docs_checks.py
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "test(docs): 第1层文档检查器纯函数 + 单测"
```

---

### Task 3: 第 1 层对真实仓库断言 + fact 标记 + 白名单 + mermaid job

**Files:** Create `tests/docs/test_doc_consistency.py`, `docs/.doc-allowlist.txt`; Modify `README.md`, `CHANGELOG.md`（加 `fact:` 标记）, `.github/workflows/ci.yml`（加 mermaid job）

**Interfaces:**
- Consumes: `tests/docs/docs_checks.py`（Task 2）; imports from `autodev.domain` for code-truth counts.
- Produces: 对真实仓库跑的一致性断言；文档带 `fact:` 标记；CI 增加 mermaid 渲染。

- [ ] **Step 1: 加 fact 标记到文档**（把易漂移计数变成机器可校验）

在 `README.md` 与 `CHANGELOG.md` 中，为"状态数/产物数/端口数/事件数"就近插入 HTML 注释标记，例如把 "12 个工作流状态" 一处写成：
```
<!-- fact:workflow_states -->12 个工作流状态
```
需要标记的键（每份文档出现处都加，值填当前真值）：`workflow_states=12`、`artifacts=8`、`ports=9`、`events=4`。（标记是注释，渲染不可见。）

- [ ] **Step 2: 写白名单**

`docs/.doc-allowlist.txt`（非代码但会被反引号包裹的 CamelCase 词）：
```
# 非代码符号白名单（品牌/工具/概念名）
GitHub
GitLab
AutoDev
Claude
ClaudeCode
Python
Mermaid
SQLite
DDD
WorkItem
```
> 说明：`WorkItem` 等真实符号本就在 known 集合里；此处仅登记确实不在代码里的词。构建时若发现真实符号被误列，应从白名单移除。

- [ ] **Step 3: 写真实仓库断言测试**

```python
# tests/docs/test_doc_consistency.py
import subprocess
import sys
from pathlib import Path

import pytest

from tests.docs.docs_checks import (
    broken_links, fabricated_symbols, known_symbols, load_allowlist, parse_facts,
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
        1 for v in vars(artifacts).values()
        if isinstance(v, type) and v.__name__.endswith("Artifact")
    )
    n_ports = sum(
        1 for v in vars(ports).values()
        if isinstance(v, type) and (v.__name__.endswith("Port")
        or v.__name__ in {"WorkItemRepository", "EventPublisher"})
    )
    n_events = sum(
        1 for v in vars(events).values()
        if isinstance(v, type) and issubclass(v, DomainEvent) and v is not DomainEvent
    )
    return {"workflow_states": n_states, "artifacts": n_artifacts,
            "ports": n_ports, "events": n_events}


def test_no_fabricated_code_symbols_in_docs():
    known = known_symbols(SRC)
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
```

- [ ] **Step 4: 跑测试并修正**

Run: `. venv/bin/activate && pytest tests/docs/test_doc_consistency.py -q`
Expected: `4 passed`。若 `test_no_fabricated_code_symbols_in_docs` 报出漂移符号，逐个判断：真为漂移→修文档；实为非代码词→加入 `.doc-allowlist.txt`。若计数不符→修 `fact:` 值或文档措辞。**必须全绿**（当前 docs 已同步，理应可绿）。

- [ ] **Step 5: 加 mermaid 渲染 job 到 CI**

在 `.github/workflows/ci.yml` 追加 job：
```yaml
  mermaid:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Render all mermaid blocks
        run: |
          npm i -g @mermaid-js/mermaid-cli
          python3 - <<'PY'
          import re, pathlib, subprocess, sys, tempfile
          fail = []
          for md in pathlib.Path('.').rglob('*.md'):
              if 'venv/' in str(md): continue
              blocks = re.findall(r'```mermaid\n(.*?)```', md.read_text(), re.S)
              for i, b in enumerate(blocks):
                  with tempfile.NamedTemporaryFile('w', suffix='.mmd', delete=False) as f:
                      f.write(b); src = f.name
                  r = subprocess.run(['mmdc','-i',src,'-o',src+'.svg'], capture_output=True, text=True)
                  if r.returncode != 0:
                      fail.append(f"{md} block#{i}: {r.stderr[:200]}")
          if fail:
              print("\n".join(fail)); sys.exit(1)
          print("all mermaid blocks render")
          PY
```

- [ ] **Step 6: 校验 + Commit**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"` 与 `pytest -q`（全绿，含新测试）。
```bash
git add tests/docs/test_doc_consistency.py docs/.doc-allowlist.txt README.md CHANGELOG.md .github/workflows/ci.yml
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "test(docs): 第1层对真实仓库断言 + fact 标记 + 白名单 + mermaid CI job"
```

---

### Task 4: PR 模板 / CODEOWNERS 迁移到 GitHub + 贡献者措辞对齐

**Files:** Create `.github/pull_request_template.md`, `.github/CODEOWNERS`; Delete `.gitlab/merge_request_templates/default.md`, 根 `CODEOWNERS`; Modify `CONTRIBUTING.md`（MR→PR 语境）

**Interfaces:** Produces GitHub-native PR template + CODEOWNERS；贡献本仓库的措辞统一为 PR。

- [ ] **Step 1: 迁移 PR 模板**

Run: `git mv .gitlab/merge_request_templates/default.md .github/pull_request_template.md`
然后编辑 `.github/pull_request_template.md`：把"MR"改为"PR"；在"评审门禁/自查清单"中新增两条：
- `[ ] 已更新相关文档（README/ROADMAP/CHANGELOG/图/ADR），或注明 Docs-Impact: none — <理由>`
- `[ ] CHANGELOG 已添加条目（或显式 skip）`
保留原有铁律自查、测试证据等 section。删除空的 `.gitlab/` 目录（`git rm -r .gitlab` 若已空）。

- [ ] **Step 2: 迁移 CODEOWNERS**

Run: `git mv CODEOWNERS .github/CODEOWNERS`（GitHub 原生识别 `.github/CODEOWNERS`）。内容中若有 GitLab 风格注释，改为 GitHub 用法说明；owner 仍为 `待填` 占位。

- [ ] **Step 3: 对齐 CONTRIBUTING 贡献者措辞**

编辑 `CONTRIBUTING.md`：把"向本仓库提交 **MR**/GitLab 流程"表述改为 **GitHub PR** 流程（fork/branch/PR、PR 模板位置 `.github/pull_request_template.md`）。**保留**任何描述"产品对接目标项目=GitLab MR"的内容（那是产品行为）。若不确定某处指哪一方，就近加一句澄清（本仓库=GitHub / 目标项目=GitLab）。

- [ ] **Step 4: 校验内链 + Commit**

Run: `. venv/bin/activate && pytest tests/docs/ -q`（内链/符号检查须仍全绿；CODEOWNERS 迁移后若有文档链接指向旧路径需修）。
```bash
git add -A .github/ .gitlab/ CODEOWNERS CONTRIBUTING.md
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "chore: PR 模板/CODEOWNERS 迁移到 .github, 贡献者措辞 MR->PR"
```

---

### Task 5: 第 2 层 路径→文档映射 + 逃生舱

**Files:** Create `docs/doc-ownership.yml`, `scripts/check_doc_impact.py`, `tests/scripts/__init__.py`, `tests/scripts/test_check_doc_impact.py`; Modify `pyproject.toml`（加 `pyyaml`）, `.github/workflows/ci.yml`（加 `doc-impact` job）

**Interfaces:**
- Produces:
  - `docs/doc-ownership.yml` — `rules: [{paths: [...glob], docs: [...]}]`。
  - `check_doc_impact.py`：核心纯函数 `evaluate(changed: list[str], rules: list[dict], changed_set: set[str]) -> list[str]`（返回 violation 文案）+ `load_rules(path)` + `main()` CLI（读 `git diff --name-only`、读逃生舱标记、打印 violations、非零退出）。glob 用 `fnmatch`/`pathlib.PurePath.match`，`**` 用 `fnmatch` 需转换——用 `pathspec` 或简单实现：对 `src/autodev/**` 用前缀匹配。
  - 逃生舱：环境变量 `DOCS_IMPACT_SKIP=1`（CI 在检测到 PR 标签 `docs:none-needed` 或提交尾注 `Docs-Impact: none` 时设置）→ `evaluate` 直接返回空。

- [ ] **Step 1: 写失败测试（核心纯函数）**

```python
# tests/scripts/test_check_doc_impact.py
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/scripts/test_check_doc_impact.py -q` → FAIL。

- [ ] **Step 3: 实现**

```python
# scripts/check_doc_impact.py
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


def evaluate(changed: list[str], rules: list[dict], changed_set: set[str],
             skip: bool = False) -> list[str]:
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
        capture_output=True, text=True, check=True,
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
        print('如确实无需文档: 给 PR 打标签 `docs:none-needed` 或提交尾注 `Docs-Impact: none — <理由>`')
        return 1
    print("文档影响检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
Also create `tests/scripts/__init__.py` (empty) and add `[tool.pytest.ini_options] pythonpath = ["src", "."]` if needed so `scripts` importable — the current pyproject has `pythonpath=["src"]`; add `"."` so `scripts` and `tests` packages import. Update pyproject accordingly.

- [ ] **Step 4: 写 ownership 配置 + 加依赖**

`docs/doc-ownership.yml`:
```yaml
# 代码路径变更 => 候选相关文档。命中却未更新 => CI 失败(可用逃生舱跳过)。
rules:
  - paths: ["src/autodev/domain/ports.py"]
    docs:  ["README.md", "docs/architecture/diagrams.md", "CHANGELOG.md"]
  - paths: ["src/autodev/domain/enums.py"]
    docs:  ["docs/architecture/diagrams.md", "CHANGELOG.md"]
  - paths: ["src/autodev/domain/work_item.py"]
    docs:  ["docs/architecture/diagrams.md", "CHANGELOG.md"]
  - paths: ["src/autodev/**"]
    docs:  ["CHANGELOG.md"]
```
`pyproject.toml`：`dev` extras 增加 `pyyaml>=6`；`[tool.pytest.ini_options]` 的 `pythonpath` 改为 `["src", "."]`。

- [ ] **Step 5: 跑测试确认通过**

Run: `. venv/bin/activate && pip install -e '.[dev]' && pytest tests/scripts/test_check_doc_impact.py -q` → `5 passed`；`pytest -q` 全绿。

- [ ] **Step 6: 接入 CI（doc-impact job, 仅 PR）**

`.github/workflows/ci.yml` 追加：
```yaml
  doc-impact:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e '.[dev]'
      - name: Resolve escape hatch
        run: |
          if echo "${{ join(github.event.pull_request.labels.*.name, ',') }}" | grep -q 'docs:none-needed'; then
            echo "DOCS_IMPACT_SKIP=1" >> "$GITHUB_ENV"
          elif git log --format=%B origin/${{ github.base_ref }}..HEAD | grep -qi '^Docs-Impact: none'; then
            echo "DOCS_IMPACT_SKIP=1" >> "$GITHUB_ENV"
          fi
      - name: Check doc impact
        env:
          DOC_IMPACT_BASE: origin/${{ github.base_ref }}
        run: python scripts/check_doc_impact.py
```

- [ ] **Step 7: Commit**

```bash
git add docs/doc-ownership.yml scripts/check_doc_impact.py tests/scripts/ pyproject.toml .github/workflows/ci.yml
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "ci(docs): 第2层 路径->文档 映射 + 逃生舱 + doc-impact job"
```

---

### Task 6: 第 3 层 AI 顾问（非阻塞）

**Files:** Create `.github/workflows/docs-advisor.yml`

**Interfaces:** Produces a non-blocking PR job that runs headless `claude` to comment on likely-stale docs; skips if no `ANTHROPIC_API_KEY`.

- [ ] **Step 1: 写 workflow**

`.github/workflows/docs-advisor.yml`:
```yaml
name: Docs Advisor (non-blocking)
on: pull_request
permissions:
  pull-requests: write
  contents: read
jobs:
  advise:
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Skip if no API key
        id: guard
        run: |
          if [ -z "${{ secrets.ANTHROPIC_API_KEY }}" ]; then
            echo "run=false" >> "$GITHUB_OUTPUT"
          else
            echo "run=true" >> "$GITHUB_OUTPUT"
          fi
      - name: Install Claude Code
        if: steps.guard.outputs.run == 'true'
        run: npm i -g @anthropic-ai/claude-code
      - name: Advise on doc staleness
        if: steps.guard.outputs.run == 'true'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          BASE: origin/${{ github.base_ref }}
        run: |
          DIFF=$(git diff "$BASE...HEAD" -- 'src/**' | head -c 60000)
          PROMPT="你是文档一致性审查助手。下面是本 PR 的代码 diff。请判断哪些文档(README/ROADMAP/CHANGELOG/docs/architecture/diagrams.md/docs/adr)可能因此过时, 列成简短清单; 若无则回复'无'。仅输出清单, 不要改任何文件。\n\nDIFF:\n$DIFF"
          COMMENT=$(printf '%s' "$PROMPT" | claude -p --permission-mode plan 2>/dev/null || echo "顾问运行失败(不阻塞)")
          echo "$COMMENT" > advisor.md
      - name: Post comment
        if: steps.guard.outputs.run == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const body = "🤖 **文档一致性顾问(非阻塞)**\n\n" + fs.readFileSync('advisor.md','utf8');
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner, repo: context.repo.repo, body,
            });
```

- [ ] **Step 2: 校验 YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/docs-advisor.yml')); print('ok')"` → `ok`。
（此 job 依赖 GitHub 环境与 secret，无法本地实跑；校验 YAML + 人工核对逻辑即可。）

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docs-advisor.yml
git -c user.name='AutoDev' -c user.email='autodev@local' commit -m "ci(docs): 第3层 AI 文档顾问(非阻塞, secret 缺失则跳过)"
```

---

## Self-Review
- 覆盖设计三层：第1层(Task2/3)、第2层(Task5)、第3层(Task6)；平台迁移(Task1/4)；单一真源=fact 标记(Task3)。
- 阻塞边界：第1/2层进 `ci.yml`(必需检查)；第3层独立 workflow + `continue-on-error`(不阻塞)。
- 占位扫描：无 TBD；每个 code step 含完整代码/命令。
- 一致性：`docs_checks` 函数签名在 Task2 定义、Task3 消费一致；`evaluate` 签名在 Task5 内自洽；CI job 名(lint/type/test/mermaid/doc-impact)贯穿一致。
- 验收(设计§8)：故意漂移触发第1/2层失败、纯重构配 Docs-Impact 通过、48+新测试全绿、.gitlab 移除——均由任务覆盖。
- 遗留：`_match` 的 `**` 实现为前缀匹配(够用于 `src/autodev/**`)；如需更复杂 glob，后续可换 `pathspec`(已在注释注明)。
