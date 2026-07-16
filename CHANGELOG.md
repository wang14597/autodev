# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Documentation-consistency CI: Layer 1 deterministic checks (`tests/docs/`) covering fabricated-symbol detection, internal-link resolution, and fact-count markers, plus a Mermaid diagram render/validation job.
- Documentation-consistency CI: Layer 2 doc-impact gate — `scripts/check_doc_impact.py` evaluates changed paths against a path-to-doc mapping in `docs/doc-ownership.yml`, wired as the `doc-impact` GitHub Actions job (PR-only). An escape hatch is available via the PR label `docs:none-needed` or a `Docs-Impact: none` commit trailer.
- Documentation-consistency CI: Layer 3 non-blocking AI docs advisor, implemented as a **local `pre-push` hook** (`scripts/docs_advise.py`, wired via the `pre-commit` `pre-push` stage) that prints a short staleness-suspect list to the developer's terminal before `git push`; it degrades gracefully (never blocks the push) whenever the environment is unavailable (no VPN, no local Claude Code session, timeout, etc.).

### Changed
- Repo CI migrated from GitLab CI to **GitHub Actions** (`.github/workflows/ci.yml`); the contribution flow for this repo is now a **GitHub PR** (fork/branch → PR) instead of a GitLab MR.
- PR template and CODEOWNERS moved to `.github/pull_request_template.md` and `.github/CODEOWNERS` respectively (`.gitlab/` and `.gitlab-ci.yml` removed).
- Layer 3 AI docs advisor changed from a GitHub Actions workflow (`pull_request`-triggered, PR-comment output, required an `ANTHROPIC_API_KEY` repo secret) to a local `pre-push` git hook, because the Anthropic key used by this project only works on the internal network and cannot be reached from GitHub's cloud runners. `.github/workflows/docs-advisor.yml` has been removed accordingly.
- Local doc advisor simplified to use Claude Code's agentic read-only investigation (`--permission-mode plan --bare`) instead of pre-computing a git diff; the script no longer gathers and truncates the diff in-process but instead delegates autonomous investigation of git changes and doc reading to Claude Code.

### Planned (Slice 2 / 后续)
- Slice 2: replace the 7 fakes-only ports (Workspace, Context, Design, Review, Execution, Verification, Delivery) with real ACL adapters + end-to-end smoke test
- GitLab MR auto-merge guards (Slice 4: trust-gradient auto-merge)
- Lark/Feishu approval workflow integration (Slice 2 Collaboration bounded context)
- Execution sandbox for Claude Code headless sessions (Slice 3)
- Prompt-injection guards for user-supplied Requirement/Context content (Slice 2/3, see Security cross-cutting concern in ROADMAP)

---

## [0.1.1] - 2026-07-16

### Added
- **Project baseline (no runtime change):** Professional project assets decoupled from feature work
  - `README.md` + `ROADMAP.md`: project face, architecture overview, current status, roadmap across all 4 slices
  - `docs/architecture/diagrams.md`: 5 Mermaid diagrams (system context, bounded contexts, state machine, sequence, data model)
  - `docs/adr/`: ADR 0001 (lightweight state machine), ADR 0002 (versioned artifacts), ADR 0003 (domain vocabulary neutralization), plus `0000-template.md` and `README.md` index
  - Governance files: `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`, `CHANGELOG.md`, `.github/pull_request_template.md`, `.github/CODEOWNERS`
  - Quality gates: `ruff` + `mypy` configuration in `pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`
  - Non-behavioral formatting/annotation pass across the existing codebase (no logic changes)

### Changed
- None (documentation/tooling only; all 48 tests and runtime behavior unchanged from 0.1.0).

### Related Documentation
- Project Baseline Plan: `docs/superpowers/plans/2026-07-15-project-baseline.md`
- ADR Index: `docs/adr/README.md`
- Architecture Diagrams: `docs/architecture/diagrams.md`

---

## [0.1.0] - 2026-07-15

### Added
- **Domain Model:** Complete DDD architecture with WorkItem aggregate root, state machine, and 7 hard rules (铁律)
  - WorkItem lifecycle: INTAKE → TRIAGE → CONTEXT → DESIGN → REVIEW → IMPL → ACCEPT → VERIFY → SUBMIT_MR → DONE
  - Value objects: RepoRef, Requirement, Verdict, GateDecision, RepoStatus, WorkspaceHandle, Cost, RetryLedger, AutonomyDial
  - Enums: TaskType, WorkflowState (<!-- fact:workflow_states -->12 states), WorkspaceMode, GatePoint, FailureKind
  - <!-- fact:artifacts -->8 versioned artifact types (TriageArtifact, ContextArtifact, DesignArtifact, ReviewArtifact, ImplArtifact, AcceptanceArtifact, VerificationArtifact, DeliveryArtifact)
  - <!-- fact:events -->4 domain events (WorkItemCreated, HumanApprovalRequested, WorkItemCompleted, WorkItemFailed)
  - 4 domain services (TriagePolicy, GatePolicy, TransitionRules, RetryPolicy)
  - <!-- fact:ports -->9 outbound ports (Protocol interfaces): WorkspacePort, ContextPort, DesignPort, ReviewPort, ExecutionPort, VerificationPort, DeliveryPort, WorkItemRepository, EventPublisher

- **State Machine Engine:** Production-grade orchestration engine
  - `Engine.advance()` (single public method) internally drives success / suspend / retry / rollback / fail / finalize outcomes; module-level `run_until_quiescent()` advances a WorkItem through consecutive stages until none are runnable
  - <!-- fact:workflow_states -->12 workflow states with legal transitions validated
  - Retry ledger and failure categorization (transient / logic / fatal)
  - Human gate (WAIT_HUMAN) as first-class state
  - Artifact versioning (append-only semantics)
  - Event publishing on every state transition

- **9 Stage Handler Functions:** Application-layer orchestration in `src/autodev/application/handlers.py`
  - `handle_intake`, `handle_triage`, `handle_context`, `handle_design`, `handle_review`, `handle_impl`, `handle_accept`, `handle_verify`, `handle_submit_mr`
  - Handler contract: `(work_item, ctx, now) -> StageOutcome`
  - Failure mapping to domain FailureKind
  - Port coordination (e.g., `handle_context` calls `ContextPort`)

- **Persistence & Event Bus:** Repository and event infrastructure
  - `SqliteWorkItemRepository`: SQLite-backed persistence (save/load/fetch-pending)
  - `InMemoryWorkItemRepository`: in-memory implementation for tests
  - `InMemoryEventBus`: publish/subscribe event bus for domain events
  - Artifact versioning storage (append-only lists per stage key)
  - Audit trail via StateTransition history

- **Test Suite:** 48 tests (unit + end-to-end walking skeleton)
  - Domain model tests (WorkItem invariants, state transitions, artifact versioning)
  - Handler tests (each stage with fake ports)
  - State machine / engine tests (all transitions, retry limits, failure routing)
  - Repository tests (persistence, event replay)
  - End-to-end walking-skeleton scenario tests (human-review path, full-auto path, failure path)

### Architecture Decisions
- **DDD with Ubiquitous Language:** All code and docs use 统一语言 terms (WorkItem, DesignProposal, Artifact, Gate, etc.); 禁止 SDK-specific leakage into core domain.
- **Hexagonal (Ports & Adapters):** Core orchestration domain defines <!-- fact:ports -->9 outbound ports; adapters implement them without polluting core logic.
- **Event-Driven Collaboration:** Domain publishes events; the Collaboration/Observability bounded contexts subscribe (decoupled) — no dedicated "CollaborationPort" exists; Collaboration is a bounded context, not a code port.
- **Append-Only Artifacts:** All stage outputs versioned per key; no overwrites. Enables audit trail and clean rollback semantics.
- **AutonomyDial:** Gate decisions parameterized per (taskType, repo, gatePoint) → auto | human; enables gradual automation rollout.

### Breaking Changes
- None (first release).

### Known Limitations
- ✋ **7 of 9 ports are fakes-only:** WorkspacePort, ContextPort, DesignPort, ReviewPort, ExecutionPort, VerificationPort, and DeliveryPort have no real adapters yet — only test fakes (future work, Slice 2). Only `WorkItemRepository` (SQLite/in-memory) and `EventPublisher` (in-memory) have real implementations.
- ✋ **No execution sandboxing:** Claude Code runs in user environment (future work, Slice 3).
- ✋ **No prompt-injection guards:** User-supplied content not yet sanitized (future work, Slice 2/3).
- ✋ **No token rotation:** GitLab/Lark tokens static during session (future work).
- ✋ **Merge gate defaults to HUMAN:** Auto-merge not enabled (future work, Slice 4).
- ✋ **SQLite only:** No multi-instance support yet; suitable for single-user/team tool (future work).

### Related Documentation
- Strategic Direction & Domain Model: `docs/architecture/2026-07-15-strategic-direction-and-domain-model.md`
- Vertical Slice Design: `docs/superpowers/specs/2026-07-15-autodev-vertical-slice-design.md`
- Slice 1 Plan (Tasks 1-13): `docs/superpowers/plans/2026-07-15-autodev-slice1-walking-skeleton.md`
- Security Policy: `SECURITY.md`
- Contributing Guide: `CONTRIBUTING.md`

---

<!-- 待填: GitHub 仓库地址（项目托管于 GitHub；远程仓库 URL 待定） -->
[Unreleased]: #
[0.1.1]: #
[0.1.0]: #
