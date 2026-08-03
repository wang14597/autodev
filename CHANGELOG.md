# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **ReviewPort 真实落地(切片 2 第 5 个真实适配器)**：`src/autodev/adapters/review_claude.py:ClaudeReviewAdapter` —— 复用 `ClaudeCodeRunner`,在 worktree 内**只读单遍**跑 `claude`,读上下文与方案两份文档并核对真实代码,产出一份**最终方案**文档(`~/.autodev/workitems/<id>/final-plan-<rand>.md`),作为下游 IMPL 的权威输入。REVIEW 由此从"判决"变为"精炼"：`ReviewArtifact` 增 `final_plan_file` 指针(默认空串,向后兼容),`handle_impl` 改取评审终稿、缺失才退回 DESIGN 初稿。判决经**首行哨兵**(`REVIEW: APPROVED` / `REVIEW: BLOCKED`)取出——`ClaudeCodeRunner` 只回 stdout,没有 `LlmTriageAdapter` 那种强制 schema 可用;首行不是哨兵即**降级为通过**并把整份输出当正文(误判通过只多走一次人审,误判回退要烧一次 `RetryPolicy` 的重试配额),通过但正文为空则报 LOGIC 失败(空方案绝不交下游)。生产组合根接入真实 `reviewer`,`IMPLEMENTED_STAGES` 扩到 REVIEW(仍止于 IMPL,该端口尚为桩);`view_detail` 增 `review` 投影,前端详情页新增「最终方案」面板与评审意见列表(blocking/suggestion 分色)。契约测试(演示评审端口 vs 真实适配器,注入假 runner)+ 解析单测 + `@pytest.mark.live` 冒烟覆盖;防漂移与安全守卫更新为 reviewer 真实、executor/verifier/delivery 仍为桩。规划见 `docs/superpowers/specs/2026-08-03-review-port-real-adapter-design.md`。
- **回退重设计不再是死路**：`DesignPort.propose` 增可选入参传入上一轮 `ReviewArtifact`,`handle_design` 在回退重设计时透传,真实设计适配器把被否理由写进提示词。此前 `RetryPolicy` 把 REVIEW 的 LOGIC 失败回退到 DESIGN,但设计端口收不到任何评审反馈——同样输入产同样方案、招来同样打回,必然烧完重试上限收敛 FAILED。该路径在演示评审端口永远通过的年代不可达,本次评审能真判回退,故一并修好。补丁本身还差一步才闭环：`handle_review` 判回退返回的 `StageOutcome.fail(...)` 不带产物键,而 `Engine._on_failure`(`src/autodev/application/engine.py`)是四个结果分支里唯一不调 `add_artifact` 的——被否的评审结论若不主动落到工作项上,`artifacts["review"]` 在回退时根本不存在,`prior_review` 通道会恒为 `None`(通道建好了但没有东西流过去)。修法：`handle_review` 判回退时先 `work_item.add_artifact("review", review)` 再 `fail`(`add_artifact` 是 append-only,后续通过的评审追加为新版本,不会被这份被否的盖住);已有跑真引擎的端到端测试锁住"回退后设计端口确实收到被否产物"这条闭环（`tests/application/test_engine.py`）。
- **手动挡(单步推进) + 阶段能力单一真源**：`WorkItem.autonomy_enabled` 从"只管上下文后决策"泛化为**节奏总开关**——开＝自动挡(AI 连续推进)，关＝手动挡(收集段仍自动跑完,之后每一步由人点「推进」)。新增 `src/autodev/webapp/drive.py` 承载三件事:阶段能力集合(**唯一真源**,替代原先 service 与 views 各存一份的手抄清单)、停因分类纯函数(终态/门禁/未建设/手动等待四态,判定顺序即优先级)、两个驱动入口(自动循环 / 单步——后者无视"手动等待"因为人已授权,其余停因抛 `InvariantError`)。新增 `POST /api/workitems/{id}/advance`(校验同步→非法态 409、执行异步→阶段可能跑数分钟);`view_detail` 新增单一投影字段 `next_action`(advance/decide/blocked/none)+ `next_stage`,前端不重复判断停因;新增 `AdvancePanel` 按四态渲染。修掉**搁浅工作项无任何恢复入口**的结构性缺陷:原有界驱动对"合法地停"(终态/挂起)与"平台还做不了该阶段"都是同一个静默 return,后者没有状态、没有入口、UI 上却与进行中无异——驱动边界每扩一次就制造一批永久失联的工作项。收敛真源后,扩容即自动解除搁浅,历史数据零迁移。`WAIT_HUMAN` 与 `GatePoint` 语义、领域状态机**均零改动**(铁律 5)。规划见 `docs/superpowers/specs/2026-07-30-manual-drive-mode-design.md` 与 `docs/superpowers/plans/2026-07-30-manual-drive-mode.md`。
- **DesignPort 真实落地(切片 2 第 4 个真实适配器)**：`src/autodev/adapters/design_claude.py:ClaudeDesignAdapter` —— 复用 `ClaudeCodeRunner`,在 worktree 内**只读单遍**跑 `claude`,产出方案 Markdown 文档,持久化到 `~/.autodev/workitems/<id>/design-<rand>.md`(路径式产物,风格对齐 `ClaudeContextAdapter`)。`DesignArtifact` 简化为单一 `design_file: str` 指针(镜像 `ContextArtifact`),移除内联字段。生产组合根(`config.py`)接入真实 `designer`;有界驱动 `RUN` 从 `{INTAKE, TRIAGE, CONTEXT}` 扩到 `{INTAKE, TRIAGE, CONTEXT, DESIGN}`(仍止于 REVIEW,该端口尚为桩)。后端 `view_detail` 新增 `design` 投影字段,前端详情页新增可折叠「方案」面板(复用泛化后的 `BriefDocument`)。契约测试(DemoDesign vs 真实适配器,注入假 runner)+ `@pytest.mark.live` 冒烟覆盖;安全守卫测试更新为 designer 真实、reviewer/executor/verifier/delivery 仍为桩。
- **上下文简报 Markdown 渲染美化**：`BriefDocument` 渲染前先剥掉模型给整份输出套的 ```` ```markdown ```` 外壳(`frontend/src/lib/markdown.ts:unwrapMarkdownFence`,真实 ```` ```bash ````/```` ```python ```` 等代码围栏不受影响),避免整段简报被当成一大块代码;接入 `highlight.js`(common)+ `marked-highlight` 做代码语法高亮(github 主题),并把简报样式重写为清爽的 GitHub 风格排版(标题分隔线、列表/行内代码/代码块/表格/引用/分隔线/链接)。DOMPurify 消毒时保留高亮 `class`。新增 `markdown.test.ts`(解包 + 渲染 5 项)。
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
- **行为变更**：`autonomy_enabled` 为关的工作项，行为从"过了 CONTEXT_GATE 便连续跑"变为"每步等人点「推进」"。这是节奏开关泛化的直接后果(见上)；自动挡行为不变。

### Fixed
- **ReviewPort 解析终审收尾（合并前最终评审）**：
  - **BLOCKER — 整份输出套 ```` ```markdown ```` 围栏时哨兵判决恒不可达**：`parse_review_output`（`src/autodev/adapters/review_claude.py`）原先直接对首行做哨兵匹配；模型偶尔会给整份评审输出套一层外层围栏（与前端 `frontend/src/lib/markdown.ts:unwrapMarkdownFence` 是同一现象），一旦如此，`splitlines()[0]` 恒是围栏行、不等于 `REVIEW: APPROVED`/`REVIEW: BLOCKED` 中任何一个，触发"首行不是哨兵→降级为通过"的兜底——`REVIEW: BLOCKED` 因此永远无法被观测到，回退重设计通道恒不触发，围栏文本还会原样写进 `final-plan-*.md`。已在解析前新增 `_strip_outer_fence`：仅当去除首尾空白后首行整体是 ```` ``` ```` 或 ```` ```<语言标记> ```` 且末行整体是 ```` ``` ```` 时才剥掉首尾两行，正文内部真实代码围栏不受影响。新增 4 项单测覆盖（套围栏+BLOCKED 判回退、套围栏+APPROVED 正文不残留围栏、正文内部代码围栏原样保留、无外层围栏行为不变）。
  - **分隔符代理判断在特定组合下静默丢正文行**：同文件"无 `---`"分支原先用"输出里是否存在 `---`"整体代理"有没有分隔符"，当模型漏写约定分隔符、而正文深处恰好有一条 `---`（如提示词要求的 `## 风险与取舍` 小节的 Markdown 水平线）、且紧邻哨兵的正文首行又恰好长得像 `- suggestion: ...` 列表项时，该行会被误吞进 `comments`、从持久化终稿里永久消失且不报错。已改为把"分隔符是否存在"的识别范围限定在紧跟哨兵的**前导块**内：从哨兵之后逐行扫描，只跨过空行与意见行前缀，遇到第一个既非空行也非意见行的行——若它整体是 `---` 才认定真分隔符；若前导块内没有紧邻的分隔符但全文深处存在 `---`，则不再猜测任何前导行是意见行，整段原样归入正文、`comments` 为空。新增单测覆盖该场景（退回修复前必然失败）。
  - 设计文档 `docs/superpowers/specs/2026-08-03-review-port-real-adapter-design.md` §3/§3.1 同步回写上述两处修复的最终结论（此前仍写着无条件 `_persist` 与"意见行之后剩余全部当正文"的旧描述）。
  - `src/autodev/adapters/demo.py` 顶部 docstring 更正为如实描述："生产对 DESIGN 及之后仍用抛错桩"已过时——DesignPort 与 ReviewPort 均已是真实适配器，仅 executor/verifier/delivery（IMPL 及之后）仍为桩。
  - 前端 `frontend/src/pages/WorkItemDetailPage.tsx`：评审判回退时页面只渲染一串 `ReviewComments`、悬空无说明。已套上与其它块一致的 `<section>` + 标题，并用上 DTO 里此前未被读取的 `approved` 字段给出语义标题（通过="评审意见"，打回="评审未通过"）；`ReviewComments` 新增可选 `approved` 入参，在被打回时渲染"评审未通过，已退回重新设计"的说明文案，并把列表项的 React `key` 从评论原文改为索引参与的 key（避免同文案评论碰撞）。新增/扩展 vitest 覆盖。
  - `tests/fakes.py` 的 `FakeReview` 打回意见此前是裸 `("rejected",)`，没有 `- blocking: ` 前缀，与生产 `_COMMENT_PREFIXES` 约定不一致；已补上前缀，新增测试锁死该约定。
- **手动挡终审收尾（合并前最终评审）**：
  - **BLOCKER — resume 落地终态时误报推进失败**：`decide_workitem` 的 `proceed` 分支曾无条件提交 runner；`resume_target(GatePoint.MERGE_GATE, "proceed")` 是 `S.DONE`（终态），手动挡下提交的 `step` 经 `ensure_advanceable`→`classify` 判定 `TERMINAL` 抛 `InvariantError`，在 `SyncExecutor` 下把"已正常完成"的 200 变成 400。已改为 resume 后重读工作项、仅当 `classify` 为 `None`/`MANUAL_HOLD` 才提交 runner；新增 `tests/webapp/test_demo_service.py` 手动挡回归用例，全程 `autonomy_enabled=False` 走完 CONTEXT/REVIEW/MERGE 三个门到 DONE，断言不抛异常（回退旧逻辑可复现该用例失败）。
  - **缺失的安全性质**：`tests/webapp/test_drive.py` 新增对 `WAIT_HUMAN` 工作项的 `ensure_advanceable`/`step` 断言——此前只验证 `DONE`/`REVIEW`，若有人把豁免从"仅 `MANUAL_HOLD`"悄悄放宽到也豁免 `WAIT_HUMAN`，全套测试仍会绿灯，「推进」就能跨过一个开着的风险门禁。
  - **控制台轮询在手动挡常驻的阶段处失效**：`frontend/src/lib/workitem.ts` 的 `isRunning`/`pollingInterval` 只覆盖 `INTAKE/TRIAGE/CONTEXT`，DESIGN 及之后（手动挡下人点「推进」后常驻数分钟的阶段）不再轮询——`POST /advance` 校验同步返回、执行异步，页面看起来像"点了没反应"。已把 DESIGN/REVIEW/IMPL/ACCEPT/VERIFY/SUBMIT_MR 也纳入轮询范围（`WAIT_HUMAN`/`DONE`/`FAILED` 仍是真正的静止态，不纳入）。
  - `tests/webapp/test_app.py` 的 `_work_item` 测试 helper 曾在 CONTEXT 后静默截断（请求 DESIGN/DONE 会拿到 CONTEXT 工作项），已比照 `tests/webapp/test_views.py` 的同名 helper 扩展到 DESIGN/REVIEW/WAIT_HUMAN/DONE；`test_advance_endpoint_returns_detail` 原先的恒真断言（`next_action in {四态}`）随之收紧为精确值 `"advance"`。
  - `ROADMAP.md` 两处过时的驱动边界描述（"止于 DESIGN"/"DESIGN 起为抛错桩"）更正为反映 DESIGN 已落地、止于 REVIEW 的现状；「并发与调度」补记 `/advance` 尚无乐观锁、双击可重复推进的已知债务。
- **「方案」阶段在 UI 上被误标「待建设」**：`views.py` 手抄了一份"未实现阶段"清单，与驱动用的那份是同一事实的第二份副本且已漂移——DESIGN 早已实现并进入驱动集合，停在上下文阶段的工作项却仍把「方案」显示为「待建设」。已删除该副本，改为消费单一真源；并加防漂移守卫测试(断言能力集合与生产组合根里"端口是否为桩"逐阶段一致)，下次谁加了真适配器忘改集合即测试失败。
- **CI 恢复为可绿(自 2026-07-16 起每次运行都失败的三处基础设施债)**：`quality` 与 `mermaid` 两个 job 一直红,且因失败发生在 `ruff format` 步骤而掩盖了下游步骤的问题,逐层暴露后一并修掉。
  - **`quality` / 格式检查**：`dev` 附加组声明 `ruff>=0.6` 无上界,本地 venv 停在 0.15.21 而 CI 每次拉最新(今解析到 0.16.0)。ruff 0.16 起会格式化 Markdown 内的 Python 代码块,于是 `ruff format --check .` 从 92 个文件扩到 127 个,判定 9 个 `docs/superpowers/**` 的 spec/plan 需重排。这些片段是示意性伪代码(刻意对齐注释、省略实现体),其一致性由文档一致性 CI 负责,故在 `pyproject.toml` 增 `[tool.ruff.format] exclude = ["**/*.md"]`,让格式化只作用于真实 Python 源码且不随 ruff 版本漂移。
  - **`quality` / 测试**：安装步骤只装 `.[dev]`,而 `tests/webapp/**` 与 `tests/adapters/test_triage_llm.py` 在模块级 `import fastapi`/`httpx`,缺依赖会在收集阶段直接报错(非 skip),3 个模块 `ModuleNotFoundError` → `pytest` 退出码 2。改为 `.[dev,web]`。
  - **`mermaid` / 环境**：`mmdc` 经 puppeteer 起无头 Chromium,GitHub runner 镜像(Ubuntu 23.10+)限制非特权用户命名空间,默认沙箱起不来(`No usable sandbox!`),5 个图全部渲染失败。CI 容器本身即隔离边界,故传 puppeteer 配置显式关掉 Chromium 内层沙箱(`--no-sandbox`)。
  - **`mermaid` / 图语法**：上述沙箱问题一直掩盖了一个真实的语法错误——`docs/architecture/diagrams.md` 第 4 张时序图的 `Note over` 文案里用了半角 `;`,而它在 `sequenceDiagram` 中是语句分隔符,导致 Note 提前结束、其后半句被当成非法语句(`Parse error on line 30`)。改用全角 `；`。同块 `classDef` 里的半角 `;` 是合法的语句终止符,不受影响。
- **控制台服务读文件失败退化为空响应(运行时事故,非代码缺陷)**：长期在后台跑的 uvicorn 进程被 reparent 到 launchd 后,失去 macOS TCC 对 `~/Downloads` 下文件的读权限;`stat()` 仍成功(响应头照常带 `content-length`)而 `open()` 抛 `EPERM`,于是 `GET /` 回 200 但**响应体 0 字节**(浏览器白屏),同时惰性 import 失败使 `/openapi.json` 报 500。无代码可修——需从有权限的父进程重启;重启后 `/` 与 `frontend/dist/index.html` 字节一致、`/openapi.json` 恢复 200。

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
