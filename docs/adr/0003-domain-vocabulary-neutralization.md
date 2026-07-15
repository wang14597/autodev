# ADR 0003: Domain Vocabulary Neutralization (Removing External System Concepts)

## Status
Accepted (2026-07-15)

## Context
**Architectural principle (铁律 #1):** The core orchestration domain must remain pure and free of external system concepts. External integrations (Git, GitLab, Feishu, Claude Code) are handled only in Anti-Corruption Layer (ACL) adapters.

**The problem:** Initial domain model inadvertently leaked Git/GitLab terminology into the core:
- `WorkspaceMode.WORKTREE | CLONE | CREATE` — Git-specific worktree/clone operations
- `WorkspaceHandle.worktree_path, branch` — Git concepts (worktree directory, branch name)
- `ContextArtifact.worktree_path, branch` — Leaks workspace execution details
- `DeliveryArtifact.mr_url, branch` — GitLab MR-specific term

**Impact:** These terms made the core domain coupling-heavy and harder to understand in isolation. The domain should reason about workspace mode semantically ("reuse existing local", "fetch from remote", "create new"), not via Git mechanisms.

## Decision
**Neutralize domain vocabulary to remove all external system references:**

| Original (Git-Coupled) | Neutralized | Semantic Intent |
|------|---|---|
| `WorkspaceMode.WORKTREE` | `WorkspaceMode.REUSE` | Reuse existing local workspace |
| `WorkspaceMode.CLONE` | `WorkspaceMode.FETCH` | Fetch/initialize from remote source |
| `WorkspaceMode.CREATE` | `WorkspaceMode.CREATE` | Create entirely new workspace (no existing local or remote baseline) |
| `WorkspaceHandle.worktree_path` | `WorkspaceHandle.location` | Path or identifier to workspace location |
| `WorkspaceHandle.branch` | `WorkspaceHandle.label` | Workspace branch/version label |
| `ContextArtifact.worktree_path` | `ContextArtifact.workspace_location` | Location of workspace used for context gathering |
| `ContextArtifact.branch` | `ContextArtifact.workspace_label` | Label of workspace branch |
| `DeliveryArtifact.mr_url` | `DeliveryArtifact.change_request_url` | URL of change request (MR/PR/etc.) |
| `DeliveryArtifact.branch` | `DeliveryArtifact.label` | Change request branch/version label |

**Localization:**
- Core domain (`src/autodev/domain/`): uses **only** neutralized names
- ACL adapters (e.g., `adapters/git_workspace.py`, `adapters/gitlab_delivery.py` — slice 2): translate between neutralized domain language and Git/GitLab APIs
- Example adapter mapping:
  ```python
  # Adapter (slice 2): Git-specific logic lives here
  def provision(work_item_id, repo, mode, label):
      match mode:
          case WorkspaceMode.REUSE:
              # Git: checkout existing worktree or branch
              result = git.worktree.list()  # Git API call
          case WorkspaceMode.FETCH:
              # Git: clone from remote
              git.clone(repo.url, ...)
          case WorkspaceMode.CREATE:
              # Git: git init new repo
              git.init()
      return WorkspaceHandle(location="/tmp/...", label=label)
  ```

## Consequences

**Positive:**
- Core domain is provider-agnostic; can be unit-tested without Git/GitLab dependencies
- Future migration scenarios (e.g., switch from GitLab to GitHub, or local filesystem to cloud storage) only require new adapters; core logic untouched
- Domain vocabulary is self-documenting ("label" conveys intent; "branch" leaks implementation)
- Easier to onboard new team members; domain model focuses on business logic, not tool details
- Compliance with six-tier architecture (Ports & Adapters); clear separation of concerns

**Negative:**
- Rename refactor across domain, tests, and documentation (one-time cost)
- Adapter layer must be careful with bidirectional translation; bugs can hide in adapter boundary
- Some loss of Git-specific semantic clarity for developers familiar with Git (e.g., "FETCH mode" less obvious than "CLONE")

**Mitigations:**
- Document mapping table (this ADR) and comment adapter implementations
- Include neutralized term definitions in ubiquitous language (domain model doc)
- Adapter tests verify translation fidelity (both directions)

## Alternatives Considered

### Keep Git Terminology (rejected)
- Proposal: Leave `WorkspaceMode.WORKTREE`, `worktree_path`, `mr_url` in domain
- Pros: No rename burden; Git-familiar developers understand immediately
- Cons: **Violates architectural principle 铁律 #1**; makes domain Git-dependent; tightly couples to GitLab; harder to support alternative VCS later
- Verdict: Architectural violation; rejected at specification phase

### Use Fully Generic Names (rejected)
- Proposal: `WorkspaceMode.MODE_A | MODE_B | MODE_C`; `WorkspaceHandle.x, y`
- Pros: Completely neutral
- Cons: No semantic clarity; developers must look up what MODE_A means; defeats purpose of ubiquitous language
- Verdict: Over-generic; makes code harder to read

### Dual Naming (rejected)
- Proposal: Use both `worktree_path` (Git-aware internal) and `location` (neutral external)
- Pros: No breaking changes; backward compatible
- Cons: Domain confusion; two names for same concept; violates DRY principle; tests must verify both paths; technical debt
- Verdict: Increases complexity without benefit

---

**Date:** 2026-07-15  
**Author(s):** AutoDev Team  
**Related:** Architecture principle 铁律 #1 (core domain purity), Ports & Adapters pattern, Slice 2 ACL implementation plan  
**Verification:** Grep for `location`, `label`, `change_request_url`, `REUSE`, `FETCH` in `src/autodev/domain/` should confirm no Git/GitLab vocab remains.  
