# LLM 分诊 + AI 自主开关 + 仅收集停靠 设计

> 日期：2026-07-27
> 状态：**已定稿**（brainstorming 决策已定；经两轮 subagent 审核 R1 REVISE→修订→R2 **APPROVE**），待用户确认后转实现计划。
>
> **审核记录（R2，2026-07-27）**：同一 reviewer 复核确认 6 项 BLOCKING 全部闭合、修订未引入新问题（薄壳 resume 对 CONTEXT_GATE 的 proceed→DESIGN 可达；旧 /approve 不触发 close 非法路径；降级产物 intent=ACTIONABLE 因规则 1 先于规则 3 不会误 finish；TriageArtifact 6 参位置序与字段序一致）。裁决 **APPROVE**。首个应写的测试(锁死最脆弱处 B1)：用 SQLite 仓储建 `autonomy_enabled=True` 的咨询类工作项 → 跑 `_bounded_drive` → 断言到 `DONE(仅收集)`，一条同时锁死「序列化 round-trip」与「drive 循环 get() 保留开关」。
>
> **审核记录（R1，2026-07-27）**：subagent 逐行核对源码后裁决 **REVISE**，6 项 BLOCKING（已全部并入）：①`autonomy_enabled` 漏进 SQLite 序列化 → 生产开关静默恒 False；②`handle_context` 契约从「恒 success」变为「可 suspend/finish」，连锁打红一批未列测试；③`create_work_item` 入口 + walking-skeleton E2E 漏加开关；④`resume` 兼容层自相矛盾且 `GATE_RESUME_TARGET` 缺 CONTEXT_GATE；⑤`engine.advance` 缺 `finish` 分发分支(会被当失败)；⑥`StageContext.triage_policy→triage` 改名的 10 处装配点未列全。另并入 NON-BLOCKING：阈值常量单一真源、tool_use 结构化输出、钉定默认模型 id、`except StageError`、collect-only 投影、咨询误判审计。**采纳「拆成 A/B 子迭代」建议**（见 §11）。
> 背景：真实使用发现——很多 WorkItem 本质是「需求收集 / 查询咨询」类，收集完上下文即达目的，**是否继续走完整流程应由用户或 AI 决定**，不该硬性推进到 DESIGN 及之后。同时切片 2.1 的硬规则分诊（关键词表）误差大，AI 时代应改为 **LLM 分诊**。本设计在切片 2.1（真实分诊 + 风险门禁 + 确定性控制台）之上演进。
> 架构基准：docs/architecture/2026-07-15-strategic-direction-and-domain-model.md；前序：docs/superpowers/specs/2026-07-25-autodev-slice2-iteration-plan-design.md

## 0. 已确认决策（brainstorming）

1. **LLM 分诊完全替换硬规则** `TriagePolicy`；分诊改为出站端口 `TriagePort`。
2. **直连 LLM API**（不走 `ClaudeCodeRunner` 子进程，太重）；模型/密钥/base_url **全走环境变量**，模型**默认取环境下可用的最新模型**，可被环境变量覆盖。
3. **新增 `autonomy_enabled` 开关**（建 WorkItem 时设，**默认关**）：
   - 关：收集上下文后**停在用户决策点**，用户选「继续 / 完成(仅收集) / 拒绝」。
   - 开：由 AI 分诊**意图**驱动——咨询类→自动收尾为「完成(仅收集)」；需落地→继续 DESIGN。
4. **enable=开继续后，下游仍走切片 2.1 的风险门禁**（高风险在 REVIEW/MERGE 仍需人审）。
5. **分诊失败（API 不可达/超时/解析失败）→ 挂起人审，不 FAILED**（不因基础设施抖动丢工作项；无硬规则兜底）。
6. 保留的确定性关键词逻辑**迁到演示/假件适配器**，供测试与浏览器 E2E 提供确定性。

## 1. 非目标

- 飞书/Lark 集成（延续排除）。
- 真实 Design/Execution/Verification/Delivery（仍属后续迭代；本设计的 E2E 走确定性演示适配器）。
- 多模型路由 / prompt 注入防护（后续）。

## 2. 流程与状态机

```
INTAKE → TRIAGE(LLM: 类型/风险/置信 + 意图) → CONTEXT(收集简报)
   → 【上下文后决策 · AutonomyPolicy】
        分诊不可用 / 置信过低      → 挂起 CONTEXT_GATE(WAIT_HUMAN)  ← 无论开关(安全兜底)
        autonomy_enabled = 关      → 挂起 CONTEXT_GATE(WAIT_HUMAN)
        开 & 意图 = CONSULTATION    → finish → DONE(仅收集)
        开 & 意图 = ACTIONABLE      → DESIGN → REVIEW …(下游风险门禁不变)
   CONTEXT_GATE 人工决策:
        proceed → DESIGN     close → DONE(仅收集)     reject → FAILED
```

**状态机改动**（`work_item.py` 的 `_build_allowed`）：
- 新增 `GatePoint.CONTEXT_GATE`。
- 新增合法转移：`CONTEXT → WAIT_HUMAN`、`CONTEXT → DONE`（自动仅收集）、`WAIT_HUMAN → DESIGN`（人工/自动选继续）。
- 既有 `WAIT_HUMAN → {IMPL, DONE}` 保留。
- 新增 `StageOutcome.finish(artifact_key, artifact)`（kind="finish"）；引擎 `_on_finish`：存产物 → 当前态转 `DONE` → `_finalize_done`。
- **[R1-B5] `engine.advance()` 必须新增 finish 分发分支**：现为 `if success / elif suspend / else _on_failure`，`finish` 会掉进 `else` 被当失败 → 直接 FAILED。须加 `elif outcome.kind == "finish": self._on_finish(...)`。

## 3. 领域层（`src/autodev/domain`，仅标准库，遵铁律 1）

### 3.1 枚举与产物
- `enums.py`：新增 `TriageIntent`（`ACTIONABLE` / `CONSULTATION`）；`GatePoint` 加 `CONTEXT_GATE`。
- `artifacts.py`：`TriageArtifact` 加 `intent: TriageIntent = TriageIntent.ACTIONABLE`（默认值，向后兼容既有构造点与持久化产物）。

### 3.2 WorkItem
- 加字段 `autonomy_enabled: bool = False`；`WorkItem.create(...)` 增可选同名参数（默认 False）。
- **[R1-B1 关键] 必须同步 SQLite 序列化**：`sqlite_repository.py` 的 `_to_dict` 写 `autonomy_enabled`、`_from_dict` 读 `d.get("autonomy_enabled", False)`。否则生产 `create_workitem` 存盘后 `_bounded_drive` 立即 `repo.get()` 重建对象会**丢掉开关值恒回落 False**，`enable=开` 路径在生产根本走不到（内存仓储按引用存原对象掩盖此 bug）。补 round-trip 测试（walking-skeleton 用的正是 SQLite）。

### 3.3 端口（`ports.py`）
- 新增 `TriagePort`（Protocol）：`classify(requirement: Requirement) -> TriageSignal`。
- 新增值对象 `TriageSignal`（`value_objects.py`，frozen）：`level: TaskType`、`confidence: float`、`risk: RiskLevel`、`intent: TriageIntent`、`signals: tuple[str, ...]`。
  - **不含 `workspace_mode`**：那是机械判断（由 RepoStatus 推出），不归 LLM。
- **移除** `policies.py` 里的硬规则 `TriagePolicy` 类。

### 3.4 策略
- `workspace_mode_for(status: RepoStatus) -> WorkspaceMode`：从 `TriagePolicy` 抽出的纯函数（REUSE/FETCH/CREATE），放 `policies.py`。
- 新增 `AutonomyPolicy`（`policies.py`，纯领域）：
  - `decide_after_context(work_item) -> PostContextDecision`（枚举/字面："suspend" | "proceed" | "finish"）。
  - 规则（**安全优先，OR 收紧**）：
    1. 无 triage 产物、或 `signals` 含 `triage-unavailable`、或 `confidence < 置信下限` → `suspend`（无论开关）。
    2. `not work_item.autonomy_enabled` → `suspend`。
    3. `intent is CONSULTATION` → `finish`。
    4. 否则 → `proceed`。
  - **早返回、严格按序**：规则 1 的安全兜底先于开关(2)与意图(3/4),保证「分诊失败/低置信 → 人审」永不被 `enable=开` 跳过。
  - **[R1-N1] 置信下限单一真源**：复用 `GatePolicy.CONFIDENCE_GATE_THRESHOLD`(0.5)，不新增第二个 0.5 常量以防漂移。
- `GatePolicy` 风险门禁**不变**（切片 2.1 的 OR-单调；下游 REVIEW/MERGE 继续生效）。

### 3.5 handlers（`application/handlers.py`）
- `handle_triage`：`signal = ctx.triage.classify(req)`；`mode = workspace_mode_for(status)`；组装 `TriageArtifact(signal.level, signal.confidence, mode, signal.risk, signal.signals, signal.intent)`。
  - **分诊失败**：**仅 `except StageError`**（基础设施失败,已在适配器边界翻译）时，`handle_triage` 产出**降级产物** `TriageArtifact(SMALL_CHANGE, 0.0, mode, RiskLevel.HIGH, ("triage-unavailable",), ACTIONABLE)` 而非让阶段失败——`AutonomyPolicy` 规则 1（低置信/unavailable）随即把它导向 `suspend`（人审），实现"失败→挂起人审"。**[R1-N5] 不得裸 `except Exception`**：非 StageError（真 bug）照旧上抛,由引擎按 TRANSIENT 重试/最终 FAILED,不被降级吞掉。
- `handle_context`：收集后调 `AutonomyPolicy.decide_after_context`：
  - `suspend` → `StageOutcome.suspend(CONTEXT_GATE, "context", artifact)`
  - `finish` → `StageOutcome.finish("context", artifact)`
  - `proceed` → `StageOutcome.ok("context", artifact)`（→ DESIGN）

### 3.6 恢复（`application/entrypoints.py`）
- **[R1-B4] 新增** `decide_work_item(id, decision: str, repo, engine, now)`，`decision ∈ {"proceed","close","reject"}`,承载真正逻辑。
- **`resume_work_item(id, approved: bool, repo, engine, now)` 签名保持不变**,改为**薄兼容壳**委托到 `decide_work_item`（`approved=True→"proceed"`，`False→"reject"`）。现有位置参数传 bool 的调用点（`test_entrypoints.py`、`test_walking_skeleton.py`、`service.approve_workitem`）无需改——**绝不把第 2 位参数改成 `decision:str`**（否则 `resume_work_item(id, True, ...)` 把 True 当 decision 静默错）。
- **[R1-B4] 用 `resume_target(gate, decision) -> WorkflowState` 取代 `GATE_RESUME_TARGET` 字典**（现字典 L16 无 CONTEXT_GATE 项，`approved=True` 恢复 CONTEXT_GATE 会 KeyError）：
  - CONTEXT_GATE：proceed→DESIGN，close→DONE，reject→FAILED
  - REVIEW_GATE：proceed→IMPL，reject→FAILED（close 非法→InvariantError）
  - MERGE_GATE：proceed→DONE，reject→FAILED
- `close`/`proceed` 到 DONE 时补 `_finalize_done`；`reject` 发 `WorkItemFailed`。

## 4. 适配器（`src/autodev/adapters`）

### 4.1 `LlmTriageAdapter`（生产，直连 API）
- 依赖：`httpx`（已在 `web` 可选组）；直接 POST Anthropic Messages API。**不引入 `ClaudeCodeRunner`**。
- 配置（环境变量）：`AUTODEV_LLM_API_KEY`、`AUTODEV_LLM_BASE_URL`（默认官方）、`AUTODEV_TRIAGE_MODEL`（模型 id）。
  - **[R1-N6] 默认钉定一个明确的当前最新模型 id，不在运行时"探测最新"**（运行时发现不确定、不可复现）。实现时读 `claude-api` skill 取当前推荐/最新 id 作默认常量，`AUTODEV_TRIAGE_MODEL` 覆盖。语义即用户所要的"用最新模型",但以可复现的钉定默认实现。
- **[R1-N4] 结构化输出用强制 `tool_use`（单工具 + JSON schema：level/risk/intent/confidence/signals），不裸解析散文 JSON**（Anthropic Messages API 无 OpenAI 式 `response_format`,裸解析脆）。
- 失败翻译：非法枚举/缺字段/tool 未调用/超时/HTTP 错误 → 边界翻译成领域 `StageError`（铁律 3）。
- **[R1-可测性] 注入 `httpx.Client`（构造函数参数）**：生产默认真 client，测试注入假 client 跑契约断言。不再抽 `LlmClient` 领域端口（`TriagePort` 已是领域抽象,再抽属过度设计）。
- max_tokens/超时/prompt 与最新模型 id：**实现阶段读 `claude-api` skill 后定稿**。
- **[R1 第6问] 内网 key 说明**：本项目 Anthropic key 仅内网可用。无 key/不可达时,惰性降级——每个工作项 `StageError`→降级→CONTEXT_GATE 人审(平台退化为人工分诊闸,可接受)。`build_env_service` 启动时缺 `AUTODEV_LLM_API_KEY` 仅打警告,不 fail-fast。CI 走假 client;`@live` 用 `AUTODEV_LIVE=1` 门控。

### 4.2 `FakeTriage`（`adapters/demo.py`，确定性）
- 内置切片 2.1 的关键词启发式（从领域迁出）：关键词→level/risk/confidence/signals；并加**意图判定**：命中 `query|question|investigate|explain|如何|为什么|是否|查询|咨询|排查` 等 → `CONSULTATION`，否则 `ACTIONABLE`。
- 供测试 + 演示组合根 + 浏览器 E2E 使用（确定性、无网络）。

## 5. 应用 / Web

- `ProjectConsoleService.create_workitem(project_id, goal, autonomy_enabled: bool = False)`；透传到 `WorkItem.create`。
- `StageContext`：`triage_policy: TriagePolicy` 字段替换为 `triage: TriagePort`。
- `app.py`：`CreateWorkItemRequest` 加 `autonomy_enabled: bool = False`；approve 端点泛化为 `POST /api/workitems/{id}/decide`（body `{action: "proceed"|"close"|"reject"}`），保留旧 `/approve`（approved→proceed/reject）以兼容 2.1 前端与测试。
- `config.py`（生产）：注入 `LlmTriageAdapter`。`demo_config.py`（演示）：注入 `FakeTriage`。
- `views.py`：`view_detail` 的 `triage` 投影加 `intent`；`view_summary` 可加 `autonomy_enabled`（供列表展示，可选）。

## 6. 前端（`frontend/src`）

- `NewWorkItemForm`：加复选框「让 AI 自主判断是否继续后续流程」（`autonomy_enabled`，默认不勾）；`createWorkItem` 传该值。
- `TriageBadge`：展示 `intent`（「需落地」/「查询咨询」）。
- `WorkItemDetailPage`：CONTEXT_GATE 挂起（`pending_gate=CONTEXT_GATE`）时，操作面板显示三键「继续后续流程 / 完成(仅收集) / 拒绝」，调 `/decide`；REVIEW/MERGE 门仍显示「批准/拒绝」。
- `api/types.ts`：`TriageView` 加 `intent`；`WorkItemDetail`/`WorkItemSummary` 加 `autonomy_enabled`；client 加 `decideWorkItem(id, action)`。

## 7. 测试

- **领域**：状态机新转移（CONTEXT→WAIT_HUMAN/DONE、WAIT_HUMAN→DESIGN）；`AutonomyPolicy.decide_after_context` 的「enable × intent × 置信/可用性」矩阵；`resume_target` 各门×动作；`workspace_mode_for`。
- **适配器**：`TriagePort` 契约测试（`FakeTriage` + `LlmTriageAdapter` 注入**假 HTTP 客户端**跑同一组断言，含解析/失败翻译）；`@pytest.mark.live` 冒烟（`AUTODEV_LIVE=1` 才跑，真打 API）。
- **应用**：demo 服务——关→停 CONTEXT_GATE；开+咨询→DONE(仅收集)；开+落地→续跑且高风险仍拦；分诊失败→挂起。
- **E2E（agent-browser，确定性演示）**：
  1. **关**：建工作项(不勾)→停在 CONTEXT_GATE →点「继续」→继续 / 或点「完成(仅收集)」→ DONE。
  2. **开 + 咨询**：勾选 + goal="排查登录为什么偶发失败" → 自动 DONE(仅收集)，intent 徽章=查询咨询。
  3. **开 + 落地高风险**：勾选 + goal="migrate auth and delete credential tokens" → 续到 REVIEW 门 → risk=HIGH 仍需人审。
- E2E 脚本扩展 `tests/e2e/browser_e2e.sh`（沿用确定性 `FakeTriage`）。

## 8. 铁律合规

1. **核心域纯净**：LLM 只在 `LlmTriageAdapter`；域内 `TriagePort` 仅协议、`AutonomyPolicy`/`GatePolicy` 纯标准库。✅
2. **一切经端口/ACL**：分诊经 `TriagePort`，实现在 `adapters/`。✅
3. **失败翻译前置**：API 异常在适配器边界→`StageError`；再由 `handle_triage` 降级→挂起人审。✅
4. **产物版本化只进不改**：`TriageArtifact` 加字段（默认值）仍走 append。✅
5. **人审一等**：CONTEXT_GATE 是新的一等人审点；开关关 / 分诊不可用均落到人审。✅
6. **支撑域产领域产物**：分诊产 `TriageArtifact`。✅
7. **失败收敛**：分诊失败不 FAILED 而挂起（可配置的、有界的人审），无无限打转。✅

## 9. 破坏性与迁移（穷举，R1 补全）

**持久化（B1）**：`sqlite_repository.py` — `_to_dict`/`_from_dict` 增 `autonomy_enabled`（旧行兜底 False）；`TriageArtifact` 加 `intent` 同步读写（旧行兜底 `ACTIONABLE`）。补两条 round-trip 测试。

**`StageContext` 改名 `triage_policy → triage`（B6，编译级，共 10 处装配点）**——逐一改注入物：
- 生产 `webapp/config.py`（注入 `LlmTriageAdapter`）
- 演示 `webapp/demo_config.py`、`tests/webapp/test_demo_service.py`、`tests/conftest.py::make_engine`、`tests/webapp/test_project_service.py`、`tests/webapp/test_service.py`、`tests/application/test_handlers_front.py`、`tests/application/test_handlers_back.py`、`tests/application/test_engine.py`、`tests/application/test_entrypoints.py`（均注入 `FakeTriage`）
- 其中 `test_handlers_front/back.py` 用 `triage_policy=` 关键字传参，改名后不改会 TypeError。

**`handle_context` 契约变更（B2）**——默认 `autonomy_enabled=False` → 一律先 suspend 到 CONTEXT_GATE。下列现有测试需改为建项时传 `autonomy_enabled=True`（否则到不了下游门/DONE）：
- `tests/application/test_handlers_front.py::test_context_provisions_workspace`（断言 kind=="success"）
- `tests/webapp/test_project_service.py::test_create_workitem_drives_to_design_and_sets_project_id`
- `tests/webapp/test_demo_service.py`（低风险→DONE、高风险 pending_gate=REVIEW_GATE、approve 两门）
- `tests/webapp/test_demo_app.py`（三个 API 流程）

**入口开关（B3）**：`entrypoints.create_work_item` 增 `autonomy_enabled: bool = False` 透传；`tests/e2e/test_walking_skeleton.py` 三例传 `True`（否则停 CONTEXT_GATE 全红）。

**resume 泛化（B4）**：删除 `GATE_RESUME_TARGET` 字典 → 用 `resume_target(gate, decision)`；`resume_work_item(approved:bool)` 保持签名作薄壳（见 §3.6）。

**引擎（B5）**：`advance` 加 `finish` 分发分支 + `_on_finish`。

**分诊测试迁移**：删除 `tests/domain/test_triage_policy.py`（原测领域 `TriagePolicy`）→ 新建 `tests/adapters/test_fake_triage.py`（测 `FakeTriage` 的关键词+意图判定）；`tests/domain/test_policies.py` 的 `test_triage_picks_workspace_mode` 改测新的 `workspace_mode_for` 纯函数。`tests/domain/test_gate_policy_risk.py` 里构造 `TriageArtifact` 处补 `intent` 参数（有默认值可不改，但新增意图相关断言）。

## 10. 审核问题与结论（R1 已闭环）

| # | 问题 | R1 结论 |
|---|------|---------|
| 1 | 兜底次序是否正确/有无绕过 | 正确;规则 1 早返回先于开关/意图,无绕过（§3.4 已明确）。 |
| 2 | 失败→降级→挂起链是否可靠、会被 enable=开跳过吗 | 可靠,不会;前提是适配器把**所有**基础设施异常翻译成 StageError 且 handle_triage **仅 except StageError**（§3.5）。 |
| 3 | resume 泛化是否破坏 2.1 /approve 与测试 | 按初稿会破坏;已改为薄壳保签名 + `resume_target` 覆盖 CONTEXT_GATE（§3.6 / B4）。 |
| 4 | finish + CONTEXT→DONE 与 `_finalize_done` 相容? | 相容（cleanup 只依赖 context 产物,delivery 缺失→url 空可接受）;**前提是 advance 加 finish 分支**（B5）。 |
| 5 | 假 HTTP 客户端够还是抽 LlmClient? | **够**;注入 `httpx.Client`,不再抽领域端口（§4.1）。 |
| 6 | 内网 key 生产/CI 差异,默认失败路径? | 稳妥但需说清:无 key→惰性降级为人工分诊闸;启动仅警告不 fail-fast;CI 假 client;`@live` 门控（§4.1）。 |

## 11. 子迭代切分（采纳 R1 建议:A 先行、B 随后）

所有**破坏性、跨切面、可确定性验证**的改动集中在 A,先落地把迁移全绿再引入外部依赖:

- **子迭代 A（确定性闭环,无网络,可 agent-browser E2E）**:`TriageIntent`/`GatePoint.CONTEXT_GATE`、`TriageSignal`/`TriagePort`、`AutonomyPolicy`、`workspace_mode_for`、`autonomy_enabled` 字段 + SQLite 序列化(B1)、状态机新转移 + `StageOutcome.finish`/`_on_finish`(B5)、resume decision 泛化(B4)、`FakeTriage`、全部 §9 迁移(B2/B3/B6)、前端开关+意图+三键面板、demo/E2E。
- **子迭代 B（真实 LLM,受网络/内网 key 约束,`@live` 门控）**:仅 `LlmTriageAdapter`（tool_use 结构化输出、失败翻译、注入 httpx.Client、契约测试 + live 冒烟）+ `config.py` 接线 + 缺 key 启动警告。

理由:A 完全离线可测,能在引入 LLM 前把状态机/持久化/兼容层迁移彻底收口;B 只是在已定型的 `TriagePort` 背后塞适配器 + 一处接线。混在一起会让"状态机迁移是否对"被"API 连不连得上"淹没。

## 12. 其他（R1 NON-BLOCKING）

- **[N2] 咨询→finish 绕过风险门是安全的**（collect-only 无 design/impl/delivery,什么都不执行）,但 LLM 误判 ACTIONABLE→CONSULTATION 会静默丢真实工作。→ `finish` 时记可审计信号/事件,便于事后发现误判;文档明写"跳过风险门因无执行"。
- **[N3] collect-only 的 DONE 观感**:`stage_views` 会把 DESIGN..SUBMIT_MR 显示 blocked。→ 加一个 collect-only 的 DONE 投影/徽章(前端),区分"仅收集完成"与"走完全流程完成"。
