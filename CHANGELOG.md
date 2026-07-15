# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Linter integration (`ruff`) — Task B5
- Type checker integration (`mypy`) — Task B5
- GitLab MR auto-merge guards — Task C2
- Lark approval workflow integration — Task C3
- SQLite persistence layer upgrades — Task C4

---

## [0.1.0] - 2026-07-15

### Added
- **Domain Model (Task B1):** Complete DDD architecture with WorkItem aggregate root, state machine, and 7 hard rules (铁律)
  - WorkItem lifecycle: INTAKE → TRIAGE → CONTEXT → DESIGN → REVIEW → IMPL → ACCEPT → VERIFY → SUBMIT_MR → DONE
  - 9 value objects (WorkItemId, TaskType, WorkflowState, Artifact, Verdict, FailureKind, etc.)
  - 4 domain services (TriagePolicy, GatePolicy, TransitionRules, RetryPolicy)
  - 8 domain events (WorkItemCreated, DesignProposed, ReviewApproved, VerificationPassed, etc.)
  - Anti-Corruption Layer (ACL) port interfaces for workspace, execution, verification, delivery, collaboration

- **State Machine Engine (Task B2):** Production-grade state machine implementation
  - 11 workflow states with legal transitions validated
  - Retry ledger and failure categorization (transient / logic / fatal)
  - Human gate (WAIT_HUMAN) as first-class state
  - Artifact versioning (append-only semantics)
  - Event publishing on every state transition
  - Backward-compatible upgrade path for future rule refinements

- **9 Stage Handlers (Task B3):** Application-layer orchestration
  - IntakeHandler, TriageHandler, ContextGatheringHandler, DesignProposalHandler, ReviewHandler
  - ImplementationHandler, AcceptanceHandler, VerificationHandler, DeliveryHandler
  - Handler contract: (WorkItem, context) → StageOutcome
  - Failure mapping to domain FailureKind
  - Port coordination (e.g., ContextGatheringHandler calls ContextPort)

- **Persistence & Event Bus (Task B3):** Repository and event infrastructure
  - SQLite-backed WorkItemRepository with save/load/fetch-pending operations
  - In-memory event bus with publish/subscribe for domain events
  - Artifact versioning storage (append-only lists per stage key)
  - Audit trail via StateTransition history

- **Test Suite (Task B3):** 48 comprehensive tests
  - Domain model tests (WorkItem invariants, state transitions, artifact versioning)
  - Handler tests (each stage with mocked ports)
  - State machine tests (all transitions, retry limits, failure routing)
  - Repository tests (persistence, event replay)
  - Minimum 80% coverage for domain/application layers

- **Governance & Collaboration Files (Task B4):**
  - `CONTRIBUTING.md`: Development setup, Conventional Commits, branch strategy, hard rules checklist
  - `SECURITY.md`: Threat model for autonomous code-writing agent; planned mitigations for execution sandbox, prompt injection, token privilege, auto-merge guards
  - `LICENSE`: Proprietary internal notice with externalization path
  - `CHANGELOG.md` (this file)
  - `.gitlab/merge_request_templates/default.md`: MR checklist against 5 hard rules + test evidence
  - `CODEOWNERS`: Placeholder for team ownership

### Architecture Decisions
- **DDD with Ubiquitous Language:** All code and docs use 统一语言 terms (WorkItem, DesignProposal, Artifact, Gate, etc.); 禁止 SDK-specific leakage into core domain.
- **Hexagonal (Ports & Adapters):** Core orchestration domain defines 8 outbound ports; adapters implement them without polluting core logic.
- **Event-Driven Collaboration:** Domain publishes events; Collaboration/Observability contexts subscribe (decoupled).
- **Append-Only Artifacts:** All stage outputs versioned per key; no overwrites. Enables audit trail and clean rollback semantics.
- **AutonomyDial:** Gate decisions parameterized per (taskType, repo, gatePoint) → auto | human; enables gradual automation rollout.

### Breaking Changes
- None (first release).

### Known Limitations
- ✋ **No execution sandboxing:** Claude Code runs in user environment (future work, Task C1).
- ✋ **No prompt-injection guards:** User-supplied content not yet sanitized (future work, Task C1).
- ✋ **No token rotation:** GitLab/Lark tokens static during session (future work, Task C1).
- ✋ **Merge gate defaults to HUMAN:** Auto-merge not enabled (future work, Task C2).
- ✋ **SQLite only:** No multi-instance support yet; suitable for single-user/team tool (future work, Task D1).

### Related Documentation
- Strategic Direction & Domain Model: `docs/architecture/2026-07-15-strategic-direction-and-domain-model.md`
- Vertical Slice Design: `docs/superpowers/specs/2026-07-15-autodev-vertical-slice-design.md`
- Security Policy: `SECURITY.md`
- Contributing Guide: `CONTRIBUTING.md`

---

[Unreleased]: https://github.com/autodev/autodev/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/autodev/autodev/releases/tag/v0.1.0
