# ADR 0001: Lightweight Bespoke State Machine as Orchestration Engine

## Status
Accepted (2026-07-15)

## Context
AutoDev orchestrates end-to-end research-to-review-to-merge workflows for unattended code generation. The core orchestration engine must:
- Support retry on transient failures (e.g., API timeouts)
- Support resume after manual review (human gates at REVIEW_GATE and MERGE_GATE)
- Support rollback and re-execution (e.g., VERIFY failure → IMPL retry → DESIGN re-emit)
- Handle concurrent attempts gracefully without losing history
- Stay small and domain-focused to enable rapid iteration (land fast principle)
- Avoid heavy abstraction overhead

Three approaches were considered:

**Approach A:** Minimal linear pipeline (no retry/resume/gate logic)
- Pros: Simplest to implement, no external dependencies
- Cons: Cannot support unattended goals without manual workaround; no retry capability; no suspend-resume pattern

**Approach C:** Mature workflow engine (Temporal, Prefect, LangGraph, Airflow)
- Pros: Battle-tested, feature-rich (retries, timeouts, observability)
- Cons: Heavy dependency burden; steep learning curve; abstraction (DAG/task model) poorly matches domain (linear flow with gates & rollbacks); overkill for slice 1

## Decision
**Build a bespoke lightweight state machine** (Approach B) as the core orchestration engine, living entirely in `application/engine.py`.

**Design principles:**
1. **Linear primary flow:** INTAKE → TRIAGE → CONTEXT → DESIGN → REVIEW → IMPL → ACCEPT → VERIFY → SUBMIT_MR → DONE
2. **Human gates:** REVIEW_GATE (after REVIEW) and MERGE_GATE (after SUBMIT_MR) can suspend to WAIT_HUMAN, awaiting human approval event
3. **Rollback paths:** VERIFY → IMPL (logic failure) and REVIEW → DESIGN (review rejected)
4. **Retry with limits:** Transient failures retry same state; logic failures rollback; fatal failures → FAILED; all capped at 3 per (state, failure-kind) pair
5. **State machine enforces legality:** Transitions guard against illegal state changes; WorkItem invariants enforce append-only artifacts and no-infinite-retry

**Engine loop:**
- `Engine.advance(work_item)` runs the handler for the current state, interprets outcome (success/suspend/failure), updates WorkItem, publishes events, saves
- `run_until_quiescent(repo, engine)` repeatedly claims runnable items and advances them until queue empty

## Consequences

**Positive:**
- Bespoke engine stays small (<300 lines), domain-aligned, easy to understand and extend
- No external orchestration dependency; changes to retry/gate logic are pure Python domain changes
- Artifact versioning and gate suspension are first-class, not bolted-on
- Full control over resume semantics (what state a human approval targets)

**Negative:**
- Must maintain state machine correctness ourselves (no battle-tested framework)
- No built-in observability/monitoring (custom telemetry needed for production)
- Concurrency handling (multiple engine instances) deferred to slice 2 (lock-based leader election or job queue)
- Cannot easily swap to a heavier engine later without refactoring all handler signatures

**Mitigations:**
- Comprehensive test coverage of state machine (domain + engine tests)
- Clear separation of "engine state logic" (TransitionRules, RetryPolicy) from "handler I/O" (ports)
- Documented extension points for alternative engine implementations

## Alternatives Considered

### Approach A: Minimal Linear Pipeline
Rejected because:
- No retry capability → cannot handle transient failures at scale
- No human gate → cannot support governance (all-or-nothing automation)
- Cannot achieve unattended goal without custom workarounds
- Slice 2 would need major refactor to add gates/retries

### Approach C: Mature Workflow Engine
Rejected because:
- Abstraction mismatch: DAG/task model (Temporal, Prefect) doesn't map cleanly to "linear flow with gates and 2-state rollbacks"
- Learning curve and integration cost high for team unfamiliar with framework
- "Land fast" principle prefers minimal dependencies; team can master bespoke engine in 1-2 weeks
- Slice 2 can selectively swap one stage's executor to a heavier engine (e.g., Claude Code runner as a Temporal activity) without changing core orchestrator

---

**Date:** 2026-07-15  
**Author(s):** AutoDev Team  
**Related:** Domain model (2026-07-15-strategic-direction-and-domain-model.md), Slice 1 Walking Skeleton plan  
