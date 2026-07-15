# Contributing to AutoDev

Welcome to AutoDev! This document describes how to set up your development environment, run tests and linters, and understand the project's architecture and coding standards.

## Development Setup

### Prerequisites
- Python 3.11+
- Git

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd autodev

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with dev dependencies
pip install -e '.[dev]'
```

## Running Tests, Linters, and Type Checks

### Run Tests
```bash
pytest -q
```

### Run Linter
```bash
ruff check .

# Auto-format
ruff format .
```

### Run Type Checker
```bash
mypy src
```

## Project Architecture

AutoDev implements a **Domain-Driven Design (DDD)** architecture organized around the concept of a `WorkItem`—a 研发任务 (dev work item) flowing through multiple stages (intake → design → implementation → verification → delivery).

For detailed architecture and strategic direction, see:
- [`docs/architecture/2026-07-15-strategic-direction-and-domain-model.md`](docs/architecture/2026-07-15-strategic-direction-and-domain-model.md)
- [ADRs](docs/adr/) — Architecture Decision Records

### Directory Conventions

```
autodev/
├── src/autodev/
│   ├── domain/           # Core domain: WorkItem, policies, events, ports.py (NO external SDK imports)
│   ├── application/      # Application services: stage handlers, orchestration engine
│   └── adapters/         # Anti-Corruption Layers (ACL) for external systems (flat, currently)
│       ├── sqlite_repository.py   # WorkItemRepository → SQLite persistence
│       ├── memory_repository.py   # WorkItemRepository → in-memory implementation
│       └── event_bus.py           # EventPublisher → in-memory event bus
├── tests/                # Test suite mirroring src/ structure
├── docs/
│   ├── architecture/     # Strategic vision & domain model
│   └── adr/              # Architecture Decision Records
└── [config files]
```

Note: port interfaces (contracts between domain & adapters) live in `src/autodev/domain/ports.py`, not a separate `ports/` package. 9 ports are defined there (WorkspacePort, ContextPort, DesignPort, ReviewPort, ExecutionPort, VerificationPort, DeliveryPort, WorkItemRepository, EventPublisher); only `WorkItemRepository` and `EventPublisher` have real adapters today (SQLite/in-memory repository, in-memory event bus). The remaining 7 (Workspace, Context, Design, Review, Execution, Verification, Delivery) are fakes-only in tests and are planned for real ACL implementations in Slice 2. There is no separate "CollaborationPort" — Collaboration is a bounded context (e.g., Feishu/Lark notifications and approvals), not a code port.

### Core Domain Rules (铁律 / Hard Rules)

以下是 7 条职责铁律中最常触及、面向贡献者的子集；完整 7 条见 `docs/architecture/2026-07-15-strategic-direction-and-domain-model.md` 第 2 节。

These are non-negotiable constraints enforced in all code reviews:

#### Rule 1: Core Domain Purity (核心域纯净)
The core domain (`src/autodev/domain/`) must **never import external SDK concepts**. No GitLab, Lark, Claude Code, or git types/fields. The domain only speaks in WorkItem, Artifact, Verdict, FailureKind, etc.

**Rationale:** Core domain must remain testable, stable, and independent of technology choices.

#### Rule 2: All External Interactions via ACL (一切外部皆 ACL)
All communication with external systems (git, GitLab, Lark, Claude, test tools) must be wrapped in **Anti-Corruption Layer (ACL) adapters** in `src/autodev/adapters/`. The domain sees only **ports** (interfaces), not implementations.

**Example:** Workspace operations flow through a `WorkspacePort` contract defined in `domain/ports.py`; the real git worktree implementation is planned for `adapters/` in Slice 2 (currently a fake/stub).

#### Rule 3: Artifact Versioning (产物只进不改 / Append-Only)
Artifacts (design docs, test results, MR details, etc.) are **version-listed per stage** and **never modified or deleted once created**. Each stage execution appends a new version; failed retries and rollbacks naturally produce audit trails.

**Enforcement:** The `WorkItem.add_artifact(key, version)` method appends; no overwrite or deletion.

#### Rule 4: Human Approval is a First-Class State (人审是一等状态)
When a gate requires human review, the WorkItem enters `WAIT_HUMAN` and pauses. Approval is not a side-effect; it's a proper domain event triggering resumption.

#### Rule 5: All Tests Required (新增/改动须带测试)
- **New feature?** Write tests first (TDD preferred) or alongside.
- **Bugfix?** Include a test that would have caught the bug.
- **Refactoring?** Verify all existing tests still pass.

Minimum coverage: 80% for new code in domain/application layers. Adapters acceptable at 60%+ (I/O mocking is often expensive).

### Conventional Commits

Use [Conventional Commits](https://www.conventionalcommits.org/) for all commits:

```
type(scope): subject

body (optional)

footer (optional)
```

**Types:**
- `feat:` New feature or behavior
- `fix:` Bug fix
- `docs:` Documentation only
- `style:` Code style (whitespace, formatting—no logic change)
- `refactor:` Code refactor (no feature change)
- `perf:` Performance improvement
- `test:` Test additions or updates
- `chore:` Build, deps, tooling, CI configuration

**Scope:** Affected module (e.g., `domain`, `adapters`, `application/handlers`).

**Examples:**
```
feat(domain): add RetryLedger to WorkItem aggregte

fix(adapters): handle SQLite connection timeout gracefully

docs(architecture): update ADR-001 on ACL contract versioning
```

### Branch Strategy

- **Main:** `main` — stable, production-ready code. All merges via reviewed MR.
- **Feature/Task:** Branch off `main` with pattern `feature/short-description` or `fix/issue-number`.
- **Slice Work:** For vertical slices (e.g., B1, B2), use `slice/b1-domain-model`.

**Workflow:**
1. Create feature branch: `git checkout -b feature/my-feature`
2. Commit with Conventional Commits
3. Push and open MR (see `.gitlab/merge_request_templates/default.md`)
4. Pass code review against the **Hard Rules** (see `.gitlab/merge_request_templates/default.md`)
5. Merge to main

## Code Review Checklist (Self-Review Before Submitting MR)

Before submitting your MR, verify against the **Hard Rules**:

- **[Rule 1]** Core domain (`domain/`) has zero external SDK imports ✓
- **[Rule 2]** All external I/O wrapped in ACL adapters (`adapters/`) ✓
- **[Rule 3]** Artifacts append-only (no overwrites or deletes) ✓
- **[Rule 4]** Human gates properly modeled (not sneaky side-effects) ✓
- **[Rule 5]** Changes include new/updated tests ✓

See `.gitlab/merge_request_templates/default.md` for the full reviewers' checklist.

## Project References

- **Strategic Direction & Domain Model:** [`docs/architecture/2026-07-15-strategic-direction-and-domain-model.md`](docs/architecture/2026-07-15-strategic-direction-and-domain-model.md)
- **Vertical Slice Design:** `docs/superpowers/specs/2026-07-15-autodev-vertical-slice-design.md`
- **ADRs:** `docs/adr/` directory
- **Security & Threat Model:** `SECURITY.md`
- **Changelog:** `CHANGELOG.md`

## Questions?

- **Architecture clarity:** Start with the Strategic Direction doc or check an ADR.
- **Merge conflicts:** Coordinate with your team; the architecture is designed for minimal conflict.
- **Rule violations:** Ask in the MR; clarifications are updates to this guide.
