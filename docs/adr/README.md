# Architecture Decision Records (ADRs)

This directory documents significant architectural decisions made during AutoDev development. ADRs capture the context, decision rationale, and consequences of choices that affect the system's long-term design and maintainability.

## ADR Index

| # | Title | Status | Date | Summary |
|---|-------|--------|------|---------|
| [0000](0000-template.md) | ADR Template | Reference | 2026-07-15 | Blank template for recording future decisions |
| [0001](0001-lightweight-state-machine.md) | Lightweight Bespoke State Machine as Orchestration Engine | Accepted | 2026-07-15 | Build a custom state machine for orchestration (Approach B) instead of minimal pipeline (A) or mature workflow engine (C) to balance simplicity, extensibility, and feature support (retry/resume/rollback) |
| [0002](0002-versioned-artifacts.md) | Append-Only Artifact Versioning for Audit Trail and Rollback Support | Accepted | 2026-07-15 | Store artifacts as version lists (`dict[key, list[artifact]]`) to maintain immutability, audit trail, and support rollback/re-execution without overwriting |
| [0003](0003-domain-vocabulary-neutralization.md) | Domain Vocabulary Neutralization (Removing External System Concepts) | Accepted | 2026-07-15 | Neutralize terminology (WorkspaceMode.REUSE/FETCH, location/label, change_request_url) to keep core domain free of Git/GitLab vocabulary; externalities handled only in ACL adapters |

## ADR Process

### When to Write an ADR
Write an ADR when:
- Choosing between multiple significant technical approaches (architecture pattern, major library, system design)
- Making a decision that constrains future work or establishes a pattern others must follow
- Documenting a principle or invariant that will guide implementation across multiple slices
- Recording a trade-off that may be revisited later

### When NOT to Write an ADR
- Bug fixes, refactorings that don't change architecture
- Local implementation details (algorithm choice, helper function design)
- Temporary decisions that are expected to change soon

### Writing Style
- **Title:** Brief, imperative (e.g., "Use X for Y")
- **Status:** Proposed → Accepted → (Deprecated | Superseded) 
- **Context:** Problem statement, forces, constraints, why this decision matters
- **Decision:** What was chosen and why
- **Consequences:** Positive and negative impacts; mitigations
- **Alternatives:** Other options considered and rejected, with brief rationale

### Review & Consensus
ADRs are accepted after discussion with the team and recorded in the architecture baseline document (2026-07-15-strategic-direction-and-domain-model.md). Changes to accepted ADRs require new ADRs (e.g., "ADR 0004: Supersede ADR 0002 because...").

---

## Related Documentation
- **Domain Model:** [2026-07-15-strategic-direction-and-domain-model.md](../architecture/2026-07-15-strategic-direction-and-domain-model.md) — authoritative north star for architecture
- **Slice 1 Plan:** [2026-07-15-autodev-slice1-walking-skeleton.md](../superpowers/plans/2026-07-15-autodev-slice1-walking-skeleton.md) — implementation tasks guiding code decisions
- **Vertical Slice Spec:** [2026-07-15-autodev-vertical-slice-design.md](../superpowers/specs/2026-07-15-autodev-vertical-slice-design.md) — refined specification translating architecture into concrete flows

---

**Last Updated:** 2026-07-15  
**Maintainers:** AutoDev Team
