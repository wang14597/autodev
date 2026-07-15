## 变更说明 (Change Description)

<!-- Brief summary of what this MR changes and why. Focus on the "why" and intended impact. -->

### 关键变更 (Key Changes)
- 
- 

### 相关上下文 (Related Context)
<!-- Any context that reviewers should understand (e.g., why this change was necessary, what problem it solves) -->

---

## 关联 (Related Specs, Plans, ADRs)

<!-- Link to any related specifications, implementation plans, or Architecture Decision Records -->
- Spec: `[if applicable]`
- Plan: `[if applicable]`
- ADR: `[if applicable]`
- Issue/Epic: `[if applicable]`

---

## 铁律自查清单 (Hard Rules Checklist)

以下是 7 条职责铁律中最常触及、面向贡献者的子集；完整 7 条见 `docs/architecture/2026-07-15-strategic-direction-and-domain-model.md` 第 2 节。

**Before submitting, verify against AutoDev's 5 hard rules:**

- [ ] **Rule 1 — 核心域纯净 (Core Domain Purity):** 
  - [ ] `src/autodev/domain/` files have **zero imports** from `adapters/`, external SDKs, or framework libraries (only stdlib + domain types)
  - [ ] No GitLab, Lark, Claude Code, or git concepts leaked into domain types/logic

- [ ] **Rule 2 — 一切外部皆 ACL (All External via ACL):**
  - [ ] All external system interactions (git, GitLab, Lark, Claude, tools) are wrapped in `adapters/`
  - [ ] Domain only sees port interfaces, not concrete implementations
  - [ ] Adapters translate between domain language ↔ external SDK

- [ ] **Rule 3 — 产物版本化 (Artifact Versioning):**
  - [ ] Artifacts are **append-only**: new versions added to lists, never overwritten/deleted
  - [ ] Implementation uses `WorkItem.add_artifact(key, version)`, not mutation
  - [ ] No code deletes or overwrites existing artifact versions

- [ ] **Rule 4 — 人审是一等状态 (Human Approval First-Class State):**
  - [ ] Human approval gates modeled as proper domain events, not side-effects
  - [ ] State machine respects `WAIT_HUMAN` and only resumes on explicit approval event
  - [ ] No sneaky automatic bypass of approval gates

- [ ] **Rule 5 — 新增/改动须带测试 (All Changes Need Tests):**
  - [ ] **New code** has accompanying unit tests
  - [ ] **Bug fixes** include a test that would have caught the bug
  - [ ] **Refactoring** passes all existing tests (no broken tests)
  - [ ] Domain/application tests: **80%+ coverage**; adapters: 60%+

---

## 测试证据 (Test Evidence)

### 本地测试 (Local Test Run)

```bash
pytest -q
# Expected output:
# ✓ X passed
# ✓ Coverage: X%
```

<!-- Paste the actual pytest output here. Example:
tests/domain/test_work_item.py::test_artifact_versioning_append_only PASSED
tests/domain/test_state_machine.py::test_invalid_transition_rejected PASSED
...
48 passed in 2.34s
-->

### 覆盖率 (Coverage)
- [ ] Domain/application coverage: ≥80%
- [ ] Adapter coverage: ≥60%
- [ ] Coverage report attached or visible in CI

### 手工测试 (Manual Test, if applicable)
<!-- If this MR requires manual integration testing, document the steps and results. -->

---

## 评审门禁 (Review Gates)

Before this MR can be merged:

- [ ] **Code Review:** At least one approval from code owner or designated reviewer
- [ ] **Architecture Review (if applicable):** For changes to `domain/`, `ports/`, or `adapters/` contracts
- [ ] **All CI Checks Pass:** (once B5 lands: `ruff check`, `mypy`, `pytest`)
- [ ] **Hard Rules Verified:** Reviewer confirms checklist above
- [ ] **No Merge Conflicts:** OR resolved by human review only
- [ ] **Commit messages:** Follow Conventional Commits format

---

## 自测笔记 (Self-Review Notes)

<!-- Any additional notes for reviewers, tricky areas to focus on, known limitations, or areas of uncertainty -->

---

**Reviewers:** @your-team (see CODEOWNERS)
**Ready for review?** Mark this MR as "draft: false" once the above is complete.
