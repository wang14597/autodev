# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **LLM 分诊落地(子迭代 B)**：`src/autodev/adapters/triage_llm.py:LlmTriageAdapter` —— `TriagePort` 的真实实现,**直连 Anthropic Messages API**(不走 `ClaudeCodeRunner` 子进程),用**强制 `tool_use`**(单工具 `record_triage` + JSON schema + `tool_choice`)拿结构化分诊,默认模型 `claude-opus-4-8`(Opus 4.8,可用 `AUTODEV_TRIAGE_MODEL` 覆盖)。鉴权两路:`ANTHROPIC_API_KEY`→`x-api-key`、`ANTHROPIC_AUTH_TOKEN`(内网网关)→`Authorization: Bearer`;base_url 取 `AUTODEV_LLM_BASE_URL`/`ANTHROPIC_BASE_URL`。注入 `httpx.Client` 便于契约测试(假 client,离线);HTTP/解析异常在 ACL 边界翻译成 `StageError`→由 `handle_triage` 降级挂起人审。生产组合根(`config.py`)接入真实分诊,缺凭据仅告警不 fail-fast;安全守卫测试确认 Execution/Verification/Design 端口在沙箱就绪前仍为桩。契约测试 7 项 + `@pytest.mark.live` 冒烟(`AUTODEV_LIVE=1` 真打网关,已验证 Opus 4.8 正确识别咨询意图)。
- **LLM 分诊 + AI 自主开关 + 仅收集停靠(子迭代 A：确定性闭环)**：面向「很多工作项只需收集需求/查询咨询、不必走完整流程」的场景。分诊改为出站端口 `TriagePort`（领域移除硬规则 `TriagePolicy`，其关键词启发式迁到 `adapters/demo.py:FakeTriage`）产出 `TriageSignal`（type/置信/风险 + 新增**意图** `TriageIntent` ACTIONABLE/CONSULTATION）；`workspace_mode_for` 从分诊抽出为纯函数。`WorkItem` 增 `autonomy_enabled` 开关（**默认关**，SQLite 序列化同步）。新增上下文后决策 `AutonomyPolicy.decide_after_context`（安全兜底优先：分诊不可用/低置信 → 挂起，先于开关与意图）+ 一等人审点 `GatePoint.CONTEXT_GATE`：**关**→收集后挂起交用户（继续/完成仅收集/拒绝）；**开**→AI 意图驱动（咨询→自动仅收集完成，落地→继续且下游仍走风险门禁）。新增 `StageOutcome.finish` + 引擎 `_on_finish`（仅收集→DONE）；`entrypoints` 加 `decide_work_item` + `resume_target`（`resume_work_item(approved)` 保签名作薄壳）；分诊失败在 `handle_triage` 降级为「低置信 + triage-unavailable」→ 挂起人审而非 FAILED。Web：`create_workitem(autonomy_enabled)`、`POST /api/workitems/{id}/decide`（proceed/close/reject）、`view_detail` 投影 intent/collect_only/pending_gate。前端：建项复选框、`TriageBadge` 意图、详情页 CONTEXT_GATE 三键面板。出站端口由 10 增至 <!-- fact:ports -->11（加 TriagePort）。可复现 E2E `tests/e2e/browser_e2e.sh` 覆盖 4 场景。规划见 `docs/superpowers/specs/2026-07-27-llm-triage-autonomy-switch-design.md`（R1 REVISE→R2 APPROVE）与 `docs/superpowers/plans/2026-07-27-llm-triage-autonomy-switch.md`。子迭代 B（真实 `LlmTriageAdapter` 直连 API）待续。
- **切片 2.1「可信分诊驱动信任门禁」+ 确定性控制台 E2E 底座**：分诊从桩升级为确定性启发式——`TriagePolicy` 依据关键词（危险/琐碎）、规模、验收缺失产出真实 `TaskType` + 置信度 + 新增 `RiskLevel`（LOW/MEDIUM/HIGH）+ 可解释 `signals`；`TriageArtifact` 增 `risk`/`signals`（带默认值，向后兼容；SQLite 序列化器同步、旧行兜底 LOW）。`GatePolicy` 变为**风险感知**：`needs_human = dial 要求 OR 风险=HIGH OR 置信<0.5`（OR 单调——风险信号只收紧、绝不放宽 dial）。新增确定性演示适配器 `src/autodev/adapters/demo.py`（`DemoWorkspace`/`DemoContext`/…/`DemoDelivery` + 按运行时 repo 名动态构造的放行 `release_all_dial` 工厂）与**独立演示组合根** `webapp/demo_config.py:build_demo_app`（内存仓储 + 演示适配器 + 真实 Triage/Gate + `FULL_DRIVE` 全生命周期驱动；生产入口绝不引用）。控制台新增 `POST /api/workitems/{id}/approve`（复用领域 `resume_work_item` + 再驱动，含 deny 路径）；`view_detail` 投影 `triage` 字段。驱动循环 `_bounded_drive` 增可注入 `run_states`（生产默认 `RUN` 止于 CONTEXT）。安全回归守卫：测试锁死生产组合根的 Execution/Verification/Design 端口在沙箱就绪前仍为 `UnavailableStage` 桩。前端新增 `TriageBadge`（type/confidence/risk/signals）+ 工作项详情页人审「批准/拒绝」按钮（`useApproveWorkItem`）。可复现浏览器 E2E：`tests/e2e/browser_e2e.sh`（agent-browser 驱动，起演示服务器→低风险自动到 DONE / 高风险挂起 WAIT_HUMAN 显示 risk=HIGH / 批准×2 到 DONE，全断言通过）。规划见 `docs/superpowers/specs/2026-07-25-autodev-slice2-iteration-plan-design.md`（经两轮 subagent 审核 R1→R2 APPROVE）。
- **默认分支选择器改用 antd**：引入 Ant Design（antd v6）+ `ConfigProvider` 主题（对齐设计令牌），项目默认分支从原生 `<select>` 换成 antd `Select`（`showSearch` 模糊搜索、更美观）。
- **切换项目默认分支**：项目详情页可从下拉(列出仓库 `origin/*` 分支)切换默认分支;切换会 fetch 校验分支存在并更新项目。新增 `WorkspacePort.list_branches`、`GET /api/projects/{id}/branches`、`POST /api/projects/{id}/branch`。之后新建工作项即基于新默认分支。
- **建工作项自动 fetch**：创建工作项时先对项目默认分支做一次 `git fetch`（best-effort，失败不阻断），保证该工作项的 worktree 基于默认分支的最新 `origin/<branch>`。（此前 fetch 只在建项目/刷新时做，工作项复用上次结果；现按需保证每个工作项都最新。）UI 术语统一为「默认分支」。
- **Project 跟踪分支 + 刷新 fetch**：Project 关联"仓库 + 跟踪分支"（创建时可显式指定分支，留空=仓库默认分支）。「刷新」现在**真正执行 `git fetch`** 把远端同步到本地（远程仓 fetch 镜像；本地仓 fetch 其 `origin`，best-effort）。新建工作项时其 worktree 以**跟踪分支的最新** `origin/<branch>` 为基点（本地无 origin 时退回本地分支）。`WorkItem` 增 `base_branch`；`Project.default_branch` 改为 `branch`；`WorkspacePort.prepare(repo, branch)` / `provision(..., base_branch)` 相应扩展。API：`POST /api/projects` 增可选 `branch`，项目 DTO 字段 `default_branch`→`branch`（含 refresh 响应）。
- **Project 一等概念（领域聚合 + 项目为中心控制台）**：新增 `Project` 领域聚合（`ProjectId`、name、repo_source、跟踪分支 `branch`、project 级 AutonomyDial）+ `ProjectRepository` 端口（SQLite/内存实现）。`WorkItem` 增 `project_id` 归属。控制台改为**两步 + 项目为中心**：先建项目（登记仓库/本地路径 + 一次性 setup 探测默认分支）→ 在项目下建多个工作项；首页项目列表 → 项目详情（其工作项 + 在此新建 + 刷新 + 删除）→ 工作项详情。**同项目共享一次性 setup**：`WorkspacePort.prepare` 建项目时准备一次，`repo_status` 短路（镜像/本地仓已就绪即跳过 `ls-remote`），第 2+ 个工作项不再重复探测/fetch。支持**删除项目**（级联删其工作项 + best-effort 清理 worktree + 移除登记）。新增 API：`GET/POST /api/projects`、`GET/POST(refresh)/DELETE /api/projects/{id}`、`POST /api/projects/{id}/workitems`。前端 Vite+React 以 Project 为中心重构导航。出站端口由 9 增至 10（加 ProjectRepository）。
- 本地项目自动登记 + worktree 直挂：创建工作项时"项目"输入若是一个本地 git 仓库目录路径，控制台自动以目录名登记进 `repo_map`（值带 `worktree:` 标记），并持久化到 `~/.autodev/repos.json`（重启仍在）。F1 见 `worktree:` 标记会**直接在你的仓库上 `git worktree add`**（共享对象库、不整仓克隆、秒级），worktree 落在 `~/.autodev/workspaces/<id>`——只在源仓 `.git` 里留可删的分支+worktree 注册，不碰你的工作目录文件。其它 repo_map 值（GitLab 远程 URL、file://、裸路径等）语义不变，仍走镜像克隆。`GET /api/projects` 反映运行时新增的项目。
- WorkItem 控制台（driving adapter，前端 + 后端）：平台面向用户的控制台，中心实体是领域聚合根 `WorkItem`。后端 `src/autodev/webapp/`（FastAPI）用真实 `WorkItem` + `SqliteWorkItemRepository` + `Engine` + F1/F3 适配器，**有界驱动**只自动跑 INTAKE→TRIAGE→CONTEXT 并止于 DESIGN（DESIGN 及之后用抛错桩，正常流程不触达）；应用服务/视图投影/路由均以注入假件单测。前端 `frontend/`（Vite + React + TypeScript，TanStack Query 轮询，React Router），以 WorkItem 为中心：创建工作项（需求 + 关联项目）→ 自动收集 → 生命周期流水线 + 上下文简报展示，多工作项并行；字体与 Markdown 渲染库本地打包（运行时零公网 CDN），自带 typecheck/oxlint/vitest/build/prettier 门禁并接入 GitHub Actions frontend job。FastAPI 生产托管 `frontend/dist`（SPA 客户端路由回退 + 目录穿越防护），未构建回退占位页、API 仍可用。新增可选依赖组 `web`（fastapi/uvicorn/httpx）与环境变量 `AUTODEV_FRONTEND_DIST`。
- `WorkItemRepository.list_all()`：只读枚举全部工作项（含终态），供控制台列表在进程重启后仍能持久展示（`claim_runnable` 排除终态，不适用）；SQLite 与内存适配器均实现。
- Workspace ACL (F1): real `WorkspacePort` implementation (GitWorkspaceAdapter) via bare repo cache + worktree — supports modes REUSE/FETCH/CREATE with idempotent provision/cleanup and git-failure→domain-StageError translation. (Not yet wired into the run loop; that is a later feature.)
- Context ACL (F3): real `ContextPort` implementation — a shared `ClaudeCodeRunner` base (subprocess invocation of the `claude` CLI with timeout/retry and transient/fatal/logic failure classification into `StageError`) plus `ClaudeContextAdapter`, which produces a Markdown context document directly via a two-pass collect→review (self-review degrades to the first pass on failure), persisted under `~/.autodev/workitems/<id>/`, outside the git worktree. Covered by a `ContextPort` contract test (`tests/adapters/test_context_contract.py`) that runs the same assertions against both `FakeContext` and the real adapter (fake runner injected), plus a `@pytest.mark.live` smoke test (skipped unless `AUTODEV_LIVE=1`) that exercises the real `claude` CLI end to end.
- Documentation-consistency CI: Layer 1 deterministic checks (`tests/docs/`) covering fabricated-symbol detection, internal-link resolution, and fact-count markers, plus a Mermaid diagram render/validation job.
- Documentation-consistency CI: Layer 2 doc-impact gate — `scripts/check_doc_impact.py` evaluates changed paths against a path-to-doc mapping in `docs/doc-ownership.yml`, wired as the `doc-impact` GitHub Actions job (PR-only). An escape hatch is available via the PR label `docs:none-needed` or a `Docs-Impact: none` commit trailer.
- Documentation-consistency CI: Layer 3 non-blocking AI docs advisor, implemented as a **local `pre-push` hook** (`scripts/docs_advise.py`, wired via the `pre-commit` `pre-push` stage) that prints a short staleness-suspect list to the developer's terminal before `git push`; it degrades gracefully (never blocks the push) whenever the environment is unavailable (no VPN, no local Claude Code session, timeout, etc.).

### Changed
- **ROADMAP 与代码对齐（2026-07-25）**：`ROADMAP.md` 补入「控制台 + Project 一等概念（0.1.2）」里程碑，切片 2 标注为进行中（`WorkspacePort`/`ContextPort` 两个真实 ACL 适配器已落地，其余 5 个仍为假件），并校准测试规模与时间线。同步在 `docs/.doc-allowlist.txt` 加入前端 antd 组件名（ConfigProvider/Select）以修复既有的伪造符号误报。
- `ContextArtifact` changed from carrying inline collected content to a **pointer**: it now holds `context_file` (path to the persisted Markdown result under `~/.autodev`) instead of embedding the context text directly in the artifact.
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
  - 9 outbound ports (Protocol interfaces): WorkspacePort, ContextPort, DesignPort, ReviewPort, ExecutionPort, VerificationPort, DeliveryPort, WorkItemRepository, EventPublisher

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
- **Hexagonal (Ports & Adapters):** Core orchestration domain defines <!-- fact:ports -->11 outbound ports; adapters implement them without polluting core logic.
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
