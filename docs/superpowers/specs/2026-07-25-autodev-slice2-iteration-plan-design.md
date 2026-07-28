# AutoDev 切片 2 迭代规划 + 首个可落地切片设计

> 日期：2026-07-25
> 状态：**已实现**（brainstorming 决策已定；经两轮 subagent 审核 R1 REVISE→R2 **APPROVE**；切片 2.1 已 TDD 落地并通过 agent-browser E2E）。
>
> **实现状态（2026-07-25）**：切片 2.1 全部落地——领域(RiskLevel/TriagePolicy/GatePolicy 风险感知)、持久化(序列化)、应用(演示适配器/放行 dial 工厂/`build_demo_app`/approve)、前端(TriageBadge/批准按钮)、可复现浏览器 E2E(`tests/e2e/browser_e2e.sh`)。后端 265 测试 + 前端 63 测试全绿，ruff/mypy/format/docs-consistency 全通过，3 个 E2E 场景断言全过。迭代 2.2–2.5 及 3.x 待续。
>
> **审核记录（R2，2026-07-25）**：同一 reviewer 复核确认 5 项 BLOCKING 全部闭合，裁决 **APPROVE**。补两条实现细节：①`DemoWorkspace` 须实现 `cleanup`(no-op)否则 finalize 时 AttributeError；②approve 后须显式再驱动(resume 不自动驱动)。最隐蔽坑：放行 dial 须按运行时 repo 名动态构造(工厂 `Callable[[str],AutonomyDial]`)，第一个写单测锁死。均已并入。
>
> **审核记录（R1，2026-07-25）**：subagent 架构评审官逐行核对源码后裁决 **REVISE**，提出 5 项 BLOCKING（已全部并入本稿）：①`TriageArtifact` 加字段须同步改 SQLite 序列化器否则静默丢字段；②低风险自动流转需注入放行 `AutonomyDial`（否则永停 WAIT_HUMAN）；③演示缺 `DemoWorkspace`；④人审恢复复用既有 `resume_work_item` 而非重造；⑤确定性组合根用独立 `build_demo_app` 工厂而非 `AUTODEV_DEMO` 环境分支（安全）。另并入若干 NON-BLOCKING（序列化 round-trip 测试、E2E 断言避浮点/避流水线中间态、dist 需重建、生产端口桩化回归测试等）。
> 背景：ROADMAP 已与代码对齐（切片 2「真实 ACL」进行中：`WorkspacePort`/`ContextPort` 已落地并接入组合根，其余 5 端口为桩，有界驱动止于 CONTEXT）。本文基于同类平台调研（Devin/OpenHands/Factory/SWE-agent/Jules/Copilot coding agent 等）与真实代码核对，规划切片 2 的后续子迭代，并详设**本次可落地、且可用 agent-browser 做 E2E** 的第一个切片。
> 架构基准：docs/architecture/2026-07-15-strategic-direction-and-domain-model.md
> 调研要点见本文第 1 节。

## 0. 非目标（本轮明确排除）

- **飞书/Lark 集成**（通知/审批/事件回调）——用户明确暂不纳入。
- **执行沙箱 Docker 化、真实 GitLab 开 MR、真实 `claude` 跑 Design/Execution**——需外部基础设施（容器/GitLab/网络+claude），**无法在单会话内可靠地用浏览器 E2E 验证**，排入后续带基础设施的迭代（见 §2）。
- 多模型路由（调研结论：agent 框架 > 模型混用，低优先）。

## 1. 调研要点（支撑本规划的结论）

同类平台横评 + SWE-bench 方法学审计，得出对 AutoDev 最相关的三点：

1. **AutoDev 的领域内核与门禁哲学（人审一等、失败收敛 FAILED、产物版本化只进不改）在赛道中是「对的」**，且被 SWE-bench 污染实证背书——"resolved ≠ correct"，高基准分是"真实可靠性"的弱代理，因此"人审门禁 + 数据驱动放门"方向正确。
2. **当前最大短板是运行时安全与验证真实化**：`ClaudeCodeRunner` 在宿主机直跑（无沙箱）；`Cost` 仅计 token（无 $/无上限熔断）；`TriagePolicy` 是桩（恒 `SMALL_CHANGE, 0.9`）；Design/Review/Execution/Verification/Delivery 仍为假件；无 CI 回读、无注入防护、无回归基准。
3. **同类最惨痛的坑是「验证不足即合并」与「成本失控」**：顶级 scaffold 在抗污染基准上仍 >25% 失败（引入 subtle regression）；Devin ACU 常 2–3× 超估。→ 任何自动合并的前置必须是"强回归验证 + CI 绿 + 成本护栏 + 风险感知的门禁"。

完整调研（含来源 URL、能力矩阵、逐产品横评）留存于本次会话调研产物，不复制入库以免文档漂移。

## 2. 切片 2 子迭代规划（研报驱动 + 排序理由）

调研给出的原始优先级是「沙箱(B1) → 真实验证+回归门(A1) → CI 回读(A4)」先行（安全底座）。**本规划做了一处有依据的重排序**：把**无基础设施依赖、可浏览器 E2E** 的领域信任信号（真实分诊 + 风险门禁 + 预算护栏）前置，把沙箱/真实执行/CI 排在其后带基础设施的迭代。

**重排序理由**：
- (a) **可验证性**：本轮交付要求用 agent-browser 做 E2E；沙箱/GitLab/live-claude 无法在会话内可靠 E2E，而领域信任信号可确定性 E2E。
- (b) **依赖顺序**：`AutonomyDial` 放门的"输入信号"来自分诊风险与预算——先把这些信号做真，才谈得上"数据驱动放门"；沙箱是**真实执行**前的门，而非**分诊/门禁**的前置。
- (c) **杠杆**：确定性控制台组合根是所有后续 E2E 与演示的公共前提，随迭代 2.1 一并交付。
- **安全立场不降级**：文档明确"沙箱(B1) 是任何**真实 Execution 落地**（迭代 2.4）的**硬前置**"——在沙箱就绪前，Execution/Verification 端口只接确定性假件，绝不在宿主机上让 AI 真实改盘。
- **[R1-NON-BLOCKING #6] 把该安全约束从散文变成回归检查**：加一条测试断言——生产组合根（`build_app_from_env`）注入的 `ExecutionPort`/`VerificationPort` 在迭代 2.4 之前**必须是 `UnavailableStage` 桩**。防止未来有人先接真实 runner 再补沙箱、把约束绕过。

| 子迭代 | 主题 | 关键端口/策略 | 基础设施依赖 | 可浏览器 E2E |
|---|---|---|---|---|
| **2.1（本次）** | 可信分诊驱动信任门禁 + 确定性控制台 E2E 底座 | `TriagePolicy`(真实)、`GatePolicy`(风险感知)、确定性组合根 | 无 | ✅ |
| **2.2** | 预算护栏 + 成本 trace（A3） | `Cost`/预算、engine 越界熔断→FAILED（铁律 7） | 无 | ✅ |
| **2.3** | 真实 Design/Review（复用 `ClaudeCodeRunner`） | `DesignPort`/`ReviewPort` | 需 live claude | 部分（需录制/存根） |
| **2.4** | 执行沙箱(B1) + 真实 Execution/Verification + PASS_TO_PASS 回归门(A1) | `ExecutionPort`/`VerificationPort`、`SandboxedRunner` | 需 Docker | 部分 |
| **2.5** | 真实 Delivery + CI 状态回读闭环（A4） | `DeliveryPort`、pipeline 回读 | 需 GitLab | 部分 |
| **3.x** | 自建回归评测 harness(B4)、注入防护 allowlist(B2)、并发编排(B3)、RAG 上下文(B5) | 横切 | 混合 | 混合 |

## 3. 首个切片（迭代 2.1）详细设计

**一句话**：把分诊做真、让门禁对"风险/置信度"敏感，并提供一个确定性组合根让控制台把工作项**完整**跑完生命周期——于是浏览器上能看到：**低风险任务自动流转到 DONE**，**高风险/低置信任务在 WAIT_HUMAN 挂起等人审**。这正面演示 AutoDev 的差异化（信任梯度 + 人审一等），且零外部依赖、可确定性 E2E。

### 3.1 领域层（`src/autodev/domain`，仅标准库，遵铁律 1）

**3.1.1 `TriageArtifact` 增风险维度**（`artifacts.py`）
```
@dataclass(frozen=True)
class TriageArtifact:
    level: TaskType
    confidence: float
    workspace_mode: WorkspaceMode
    risk: RiskLevel          # 新增：LOW/MEDIUM/HIGH
    signals: tuple[str, ...] # 新增：可解释的分诊依据（如 "keyword:refactor", "scope:multi-file"）
```
- 新增 `RiskLevel(Enum)`：`LOW/MEDIUM/HIGH`（`enums.py`）。
- `signals` 让分诊结果可解释（控制台展示、审计），呼应调研"可审计计划"最佳实践。
- **向后兼容**：`risk`/`signals` 加默认值，避免破坏已持久化产物与现有构造点。
- **[R1-BLOCKING #1] 必须同步改 SQLite 序列化器**：产物走 `adapters/sqlite_repository.py` 手写 JSON 编解码（`_artifact_to_dict`/`_artifact_from_dict` 对 `TriageArtifact` 逐字段列举），不改就会 **静默丢弃** `risk`/`signals`，刷新/重启后徽章变空。改动同一提交内：写入侧存 `risk`(`.name`)、`signals`(list)；读取侧对旧行 `d.get("risk", "LOW")` / `d.get("signals", [])` 兜底。补一条 round-trip 单测：旧 dict（无 risk 键）可反序列化为默认 LOW。
- **[R1] 视图投影须暴露 triage 字段**：`webapp/views.py` 现有 `view_summary` 只出 `type`/`state`，不含 confidence/risk/signals；`view_detail` 需从 `wi.artifacts["triage"]` 投影出 `triage` 字段供前端徽章渲染。

**3.1.2 `TriagePolicy` 从桩升级为确定性启发式**（`policies.py`）
- 输入 `Requirement`（含 `goal`/`raw_text`/`acceptance_hints`）+ `RepoStatus`。
- 输出：`TaskType`（SMALL_CHANGE/MEDIUM_FEATURE/COMPLEX_FEATURE，依赖现有枚举，先确认 `TaskType` 成员）、`confidence`、`risk`、`signals`。
- **纯确定性启发式**（无网络、无 AI，保证可重复 → 可 E2E 断言）：
  - 关键词信号：`refactor|migrate|delete|drop|security|auth|payment|credential` → 抬高风险；`typo|rename|comment|doc|test` → 降风险、SMALL_CHANGE。
  - 规模信号：`raw_text` 提及多文件/跨模块措辞 → MEDIUM/COMPLEX。
  - 缺失验收提示 / 目标含糊 → 降 confidence。
  - `workspace_mode` 维持现逻辑（local→REUSE, remote→FETCH, else CREATE）。
- 规则表集中、数据化，便于测试与后续替换为 AI 分诊（端口不变）。

**3.1.3 `GatePolicy` 风险感知**（`policies.py`）
- 现状：`decide` 仅凭 `autonomy_dial.needs_human(type, repo, gate)`。
- 升级：即便 dial 判定 auto，若该工作项 `TriageArtifact` 的 `risk == HIGH` **或** `confidence < 阈值`，仍强制 `needs_human=True`，`reason` 说明触发原因。
  - 读取方式：`GatePolicy.decide(work_item, gate)` 从 `work_item.artifacts["triage"]` 取（TRIAGE 一定先于任何门发生；无 triage 时按现有"type unknown→human"兜底）。
- **[R1-BLOCKING #3 澄清] 单调性必须实现为 OR，不得为 AND**：`needs_human = dial_needs_human OR risk==HIGH OR confidence<阈值`。绝不能写成会清除 `dial_needs_human` 的形式（那会把"更谨慎"变成"更激进"，反向绕过）。阈值抽成命名常量（如 `CONFIDENCE_GATE_THRESHOLD = 0.5`）便于测试。`risk` 默认 LOW 时退化为纯 dial 行为，仍单调。
- 语义：**AutonomyDial 是"允许自动的上限"，风险信号可进一步收紧但不放宽**（安全单调性）——放门只会更谨慎，永不因逻辑更激进。

### 3.2 应用层（`src/autodev/application` + `webapp`）

**3.2.1 确定性演示适配器**（新增 `src/autodev/adapters/demo.py`，生产侧、不 import `tests/`）
- 提供 **`DemoWorkspace`** + `DemoContext/DemoDesign/DemoReview/DemoExecution/DemoVerification/DemoDelivery`：确定性、无网络、无 AI、瞬时返回合法产物（形状同 `ContextArtifact`/`DesignArtifact`/…）。
- **[R1-BLOCKING #3] `DemoWorkspace` 不可省**：`create_project` 调 `WorkspacePort.prepare`、`handle_context` 调 `provision`；若演示根沿用 `GitWorkspaceAdapter` 就会要求真实可达仓库/镜像，零依赖 E2E 立即失败。`DemoWorkspace`：`prepare` 返回固定分支、`provision` 返回临时 handle、`repo_status` 返回 `exists_local=True`、`list_branches` 返回固定集合、**`cleanup` 为 no-op**。
  - **[R2 新增] `cleanup` 不可漏**：MERGE_GATE→DONE 时 `engine._finalize_done` 会调 `ctx.workspace.cleanup(...)`（engine.py），缺失会在 approve→DONE / 自动流 SUBMIT_MR→DONE 时 AttributeError。`FakeWorkspace` 有此方法，照抄。形状可借鉴 `tests/fakes.py:FakeWorkspace`，但落 `adapters/` 生产侧、不 import `tests/`。
- `DemoContext.gather` 产出一个真实存在的临时 Markdown 文件路径（写入 `AUTODEV_HOME` 下），使 `view_detail` 的简报渲染不落空（`view_detail` 对读文件失败已 `OSError→""` 兜底，故写文件是加分项非阻塞）。
- 目的：让 DESIGN 及之后阶段有确定性实现，控制台可完整驱动生命周期——**与桩 `UnavailableStage` 互补**（桩用于生产默认，演示适配器仅用于独立演示组合根）。

**3.2.2 独立演示组合根 `build_demo_app` + 放行 dial + 非有界驱动**（新增 `webapp/demo_config.py`，改 `webapp/service.py`）
- **[R1-BLOCKING #5] 用独立工厂 `build_demo_app()`，不用 `AUTODEV_DEMO=1` 环境分支**：env 分支让假适配器与生产装配路径共用，一个误设变量即可在生产端上假件，违背"沙箱是真实执行硬前置"的安全立场。独立工厂 + 生产入口（`__main__`/`build_app_from_env`）**完全不引用**它，从结构上杜绝误用。E2E 显式调用 `build_demo_app`。
- `StageContext` 全注入演示适配器（含 `DemoWorkspace`）；`GatePolicy`/`TriagePolicy` 用**真实**实现（这正是要 E2E 的对象）。
- **[R1-BLOCKING #2] 演示建项必须注入放行的 `AutonomyDial`**：`ProjectConsoleService.create_workitem` 现硬编码 `AutonomyDial.all_human()`，叠加"只收紧"的风险门禁 → 低风险项也永停 WAIT_HUMAN，永远到不了 DONE，§4 场景 1 失败。演示服务须为演示项目名构造 **对全部 (TaskType, repo, GatePoint) 组合放行** 的 dial（`needs_human` 按三元组精确匹配，key 里 repo 名须等于演示项目名）。如此才能干净证明：**是"风险 HIGH"而非 dial 把高风险项挡在人审**——低风险 dial 放行 + 风险 LOW → auto → DONE；高风险即便 dial 放行 + 风险 HIGH → 仍 suspend。为此给 `create_workitem` 增可注入的 dial 工厂参数（生产默认仍 `all_human`）。
  - **[R2 最隐蔽的坑] dial 工厂必须按运行时 repo 名动态构造**：签名 `Callable[[str], AutonomyDial]`（入参=该工作项的 `project.name`），在建项时用**该工作项实际 repo 名**生成覆盖全 `TaskType`×全 `GatePoint` 的放行 dial。**不能硬编码某个固定项目名**——`needs_human` 精确匹配三元组，换个项目名就命中不了、低风险项照停 WAIT_HUMAN，场景 1 静默失败。**第一个写单测锁死**：同名放行、异名不放行。
- 驱动：演示根允许跑完全部阶段（不再 `RUN={INTAKE,TRIAGE,CONTEXT}` 有界）——下游已是确定性演示适配器，不会触达抛错桩。实现上给 `_bounded_drive` 增可注入的"可运行阶段集合"参数，演示传全集；生产默认仍止于 CONTEXT。引擎在 WAIT_HUMAN 自然停下（`is_runnable()` 为假），正好演示人审挂起。
- **不改领域引擎语义**，只接线 + 放宽 webapp 驱动边界（受注入参数控制）。

**3.2.3 人审恢复入口——复用既有 `resume_work_item`，不重造**
- **[R1-BLOCKING #4]** `application/entrypoints.py:resume_work_item(work_item_id, approved, repo, engine, now)` 已存在且正确：approve→`resume_to(GATE_RESUME_TARGET[gate])`，`target is DONE` 时补调 `engine._finalize_done`（发 `WorkItemCompleted` + workspace cleanup）；deny→`resume_to(FAILED)` + 发 `WorkItemFailed`。**裸调 `work_item.resume_to(DONE,...)` 会绕过 finalize，不可取**。
- 新增 `POST /api/workitems/{id}/approve`（可含 `{approved: bool}`）：调 `resume_work_item`，随后继续演示驱动至 quiescent。顺带获得 deny 路径。
  - **[R2] approve 后必须显式再驱动**：`resume_work_item` 对 REVIEW_GATE 只 `resume_to(IMPL)` 不驱动；端点须在其后调用注入了全阶段集的演示 `_bounded_drive`，工作项才会继续跑到 DONE。
- **[R1 范围] approve 端点 + 前端按钮 + "点批准→DONE"场景是本切片"第一顺位可砍"项**（复用成本低故默认纳入；预算吃紧则移入 2.2）。**但放行 dial（#2）不可砍**——否则场景 1 崩，差异化演示失败。

### 3.3 前端（`frontend/src`）

- **工作项详情**展示分诊结果：`TaskType` 徽章 + `confidence` + `risk`（颜色分级）+ `signals` 列表。落点：`WorkItemDetailPage` / 复用 `StatusBadge` 或新增 `TriageBadge`（带 CSS module + vitest）。
- 生命周期流水线（`LifelinePipeline`）已能显示各状态含 WAIT_HUMAN——确认 WAIT_HUMAN 有清晰视觉（挂起态标识）。
- 若纳入 approve 端点：WAIT_HUMAN 时详情页出现「批准继续」按钮（hook `useApproveWorkItem` + 乐观刷新）。
- 视图数据经 `webapp/views.py` 的投影补充 triage 字段（`view_detail`）。

### 3.4 数据流（迭代 2.1，演示组合根）
```
建项目 → 建工作项(goal 文本)
  → INTAKE(需求完整?) → TRIAGE(真实分诊: type/confidence/risk/signals)
  → CONTEXT(DemoContext 写简报) → DESIGN/REVIEW(DemoDesign/Review)
      └─ REVIEW 门: GatePolicy(风险感知) → 高风险/低置信 ⇒ suspend WAIT_HUMAN
  → IMPL/ACCEPT/VERIFY/SUBMIT_MR(Demo*) → MERGE 门 → DONE
控制台轮询 → 前端可视化状态推进 + 分诊徽章 + 人审挂起
```

## 4. E2E 测试策略（agent-browser）

- **被测系统**：独立 `build_demo_app` 起真实 FastAPI + 真实引擎/仓储/前端 dist + 演示适配器 + **真实 Triage/Gate** + 放行 dial。确定性、无网络、无 token 消耗。
- **启动**：临时 `AUTODEV_HOME`（隔离 sqlite/workspaces）、`uvicorn` 后台起在**探测到的空闲端口**、`AUTODEV_FRONTEND_DIST` 指向 `frontend/dist`。
- **[R1-NON-BLOCKING] 前置：先 `npm run build` 重建 dist**——否则 dist 不含新的 TriageBadge/批准按钮，断言必挂。实现计划把重建列为 E2E 第一步。
- **agent-browser 场景**：
  1. **自动流**：建项目 → 建低风险工作项（goal="fix typo in README"）→ 断言 **state 徽章**最终为 DONE，无 WAIT_HUMAN。
  2. **人审门**：建高风险工作项（goal="migrate auth to new credential store and delete old tokens"）→ 断言分诊徽章显示 **risk=HIGH** 且 **state 徽章为 WAIT_HUMAN**。
  3.（若含 approve）点「批准继续」→ 断言 state 徽章推进到 DONE。
- **[R1-NON-BLOCKING] 断言稳健性**：断在 **state 徽章文本**（`view_summary.state` 已含 WAIT_HUMAN）与 **risk 稳定 token**（"HIGH"/"高"）+ 终态字符串；**不要**断 confidence 浮点、**不要**断流水线阶段 current——因 `views.py:_UNIMPLEMENTED` 把 DESIGN..DONE 标 blocked、且 WAIT_HUMAN 不在 `_CHAIN` 里，流水线阶段视觉在演示模式不可靠（除非把 `stage_views` 改为演示感知，属可选）。
- E2E 脚本与运行说明纳入实现计划，产物落 `tests/e2e/`（由实现计划定）。
- **同时保留后端 pytest 单测**（TDD）：TriagePolicy 各信号、GatePolicy 风险 OR-单调性、演示适配器契约、序列化 round-trip（旧行无 risk 键）、approve 端点、驱动跑到 DONE/WAIT_HUMAN 的应用层测试（注入假件，不依赖浏览器）。

## 5. 铁律合规性检查

1. **核心域纯净**：分诊/门禁逻辑纯标准库；`RiskLevel` 是领域枚举；无外部 SDK。✅
2. **一切经端口/ACL**：演示适配器实现既有端口协议，放 `adapters/`。✅
3. **失败翻译前置**：演示适配器不产生外部异常；真实适配器边界翻译不变。✅
4. **产物版本化只进不改**：`TriageArtifact` 加字段（附默认值）仍走 `add_artifact` append。✅
5. **人审一等**：本切片正是强化 WAIT_HUMAN 门禁；无人值守=关该门（dial 放 auto 且风险 LOW）。✅
6. **支撑域产领域产物**：分诊产 `TriageArtifact`。✅
7. **失败收敛 FAILED**：不新增无限循环；驱动在终态/挂起自然停。✅

## 6. 审核问题与结论（R1 已闭环）

| # | 问题 | R1 结论 |
|---|------|---------|
| 1 | 重排序是否得当、安全立场是否稳 | **得当**，前提是"沙箱前不接真实 Execution"由构造保证——已加回归测试锁死（§2）。 |
| 2 | 2.1 是否纳入 approve 端点/前端按钮 | **默认纳入**（复用 `resume_work_item` 成本低）；但为"第一顺位可砍"项，预算吃紧移入 2.2；放行 dial 不可砍。 |
| 3 | 风险门禁单调性是否正确、有无绕过 | 正确，**必须实现为 OR**（§3.1.3 已明确）；无 triage 走 type-unknown 兜底；无绕过。 |
| 4 | env 分支 vs 独立工厂 | **独立 `build_demo_app` 工厂**更安全（§3.2.2）。 |
| 5 | E2E 样例可否稳定触发、断言是否脆弱 | 关键词启发式对给定样例确定；断 risk token + 终态，不断浮点/流水线中间态（§4）。 |
| 6 | 有无阻断会话内实现+E2E 的隐藏依赖 | 有——序列化器(#1)、DemoWorkspace(#3)、放行 dial(#2)、dist 重建、临时 HOME+空闲端口；均已并入。 |

## 7. 会话内交付边界（诚实声明）

- 本切片刻意选择**零外部基础设施**（无 Docker/GitLab/live-claude），确保"实现 + agent-browser E2E"能在单会话内闭环。
- 真正的自主编码能力（真实 Design/Execution/Verification/Delivery）在 2.3–2.5，需基础设施，**不在本切片承诺范围**——本切片交付的是"可信分诊 + 信任门禁 + 可端到端演示与验证的确定性控制台"，是通向无人值守的**信任信号底座**，而非无人值守本身。
