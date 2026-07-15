# ADR 0002: Append-Only Artifact Versioning for Audit Trail and Rollback Support

## Status
Accepted (2026-07-15)

## Context
WorkItem produces artifacts at each orchestration stage: TRIAGE, CONTEXT, DESIGN, REVIEW, IMPL, ACCEPT, VERIFY, DELIVERY. These artifacts capture the state of work at each step.

A core domain principle is **"产物只进不改"** (artifacts only forward, never backward) — ensuring immutability for audit trail and replaying decisions.

However, the orchestration flow supports **rollback and re-execution**:
- If VERIFY fails (logic error, e.g., tests don't pass), rollback IMPL and retry
- If REVIEW rejects design, rollback DESIGN and re-run  
- In both cases, the same stage key (e.g., "design", "impl") needs to produce a new artifact version while preserving prior versions

**The conflict:** 
- Domain requirement: once an artifact is produced, never change it
- Orchestration requirement: retry/rollback may re-execute a stage, producing a new version of the same artifact key
- Naive solution (one key = one artifact) breaks audit trail; re-execution overwrites prior decision
- Naive solution (distinct key per attempt, e.g., "impl_v1", "impl_v2") pollutes the domain model; readers must hunt through version keys

## Decision
**Use versioned artifacts: `artifact_versions: dict[str, list[Artifact]]`**

**Design:**
- Each WorkItem maintains `artifact_versions` as a dict mapping stage key (string) to a list of artifacts
- `add_artifact(key, artifact)` appends to that key's version list (never overwrites or deletes)
- `current_artifact(key)` returns the latest (last) version of that key
- `artifacts` property provides a convenience view: dict[key → latest version]
- `versions_of(key)` returns the full history tuple for audit/inspection

**Example:**
```
WorkItem.artifact_versions = {
  "design": [
    DesignArtifact(change_summary="fix typo in user.py", ...),  # v1, from DESIGN stage
    DesignArtifact(change_summary="fix typo in user.py + docstring", ...),  # v2, after REVIEW rejected v1
  ],
  "impl": [
    ImplArtifact(diff="...", test_passed=False, ...),  # v1, from IMPL stage  
    ImplArtifact(diff="...fixed...", test_passed=True, ...),  # v2, after VERIFY rolled back
  ],
  "verify": [
    VerificationArtifact(verdict=Verdict(passed=False, ...), ...),  # v1, failed
    VerificationArtifact(verdict=Verdict(passed=True, ...), ...),  # v2, passed after rollback
  ],
}

WorkItem.artifacts["design"]  # → v2 (latest)
WorkItem.versions_of("design")  # → (v1, v2)
```

**Invariant enforcement:** In WorkItem, `add_artifact` enforces append-only; raises `InvariantError` if caller attempts direct list mutation.

## Consequences

**Positive:**
- Audit trail: full history of each stage's output preserved; easy to understand what changed and why (commit log)
- Rollback traceability: when IMPL rolls back after VERIFY failure, the new IMPL version is automatically a fresh entry; no confusion about "which version is current"
- Serialization-friendly: straightforward to persist (JSON) and query versions
- Domain purity: core model uses neutral "artifact_versions", not git/MR specific terms

**Negative:**
- Slightly more memory overhead (all prior versions retained in memory during single WorkItem's lifetime)
- Callers must use `.current_artifact(key)` or `.artifacts[key]` to get the right version; direct dictionary access would retrieve all versions and cause confusion
- Schema migration complexity if artifact structure changes between versions (handled by adapter layer, not core domain concern)

**Mitigations:**
- For long-running WorkItems (e.g., hours of retries), consider archive/truncate strategy in slice 2
- Serialization adapter (SQLite) can compress old versions if needed
- Clear API: `current_artifact` is the primary path for readers; old versions accessed via explicit `versions_of` call

## Alternatives Considered

### Overwrite-on-Redo (rejected)
- Proposal: `artifact_versions[key] = new_artifact` (plain dict, no history)
- Pros: Minimal memory, familiar dict semantics
- Cons: Loses audit trail entirely; cannot inspect prior design decisions; violates "only forward" principle; hard to debug why VERIFY succeeded on v2 but failed on v1

### Distinct Key Per Attempt (rejected)
- Proposal: `artifact_versions["impl_1"]`, `artifact_versions["impl_2"]`, etc.
- Pros: All versions live in same dict
- Cons: Domain code must enumerate keys, hunting for "impl_*" to find latest; orchestration layer must manage versioning; schema explosion; readers must know versioning convention
- Verdict: Pollutes domain with orchestration detail

### Separate Version Store (rejected)
- Proposal: `artifact_versions` in a separate table/dict, indexed by (WorkItemId, key, version_number)
- Pros: Clean separation of concerns
- Cons: Adds fetch/join overhead during handler logic; complicates WorkItem aggregate boundary; versioning logic spread across domain and persistence layer
- Verdict: Breaks aggregate cohesion

---

**Date:** 2026-07-15  
**Author(s):** AutoDev Team  
**Related:** ADR 0001 (state machine rollback paths), Domain principle "产物只进不改", WorkItem aggregate design  
