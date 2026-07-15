# AutoDev — 战略方向与领域模型（架构基准）

> 日期：2026-07-15
> 状态：权威架构基准（North Star）。后续所有切片的设计与实现都必须符合本文档；如需偏离，先修订本文档再动代码。
> 关联：实现范围见 `docs/superpowers/specs/2026-07-15-autodev-vertical-slice-design.md`（第一垂直线，须符合本文档）。

## 0. 为什么要有这份文档（战略意图）

AutoDev 的目标是把一个标准研发团队的工作（需求 → 上下文 → 方案 → 评审 → 开发 → 验收标准 → 验收 → 提 MR 合并）借助 AI 做到自动化、规模化、效率化，终极形态是**全自动无人值守**。

这类系统最大的风险不是"第一版做不出来"，而是"边做边改架构、越改越乱，最终无法持续迭代"。因此我们**在一开始就用 DDD 把战略方向、领域边界、职责规范钉死**，让之后的每一次迭代都是"在既定骨架上加深某个上下文"，而不是推翻重来。

本文档就是这个骨架。它约束的是**边界与职责**，不约束具体实现技术的细节演进。

## 1. 定位与约束（不可动摇的前提）

- **面向对象**：内部团队自用工具。取舍原则 = 优先落地、够用、快见效；不追求多租户/通用产品化/生产级健壮性。
- **集成环境**：代码托管 **GitLab**（MR）；协作/需求/通知/文档/审批在 **飞书 / Lark**。
- **自动化程度**：架构按**全自动无人值守**设计；投产按**信任梯度**放开。"是否需人确认"是每类任务·每仓库可配的开关（AutonomyDial）。
- **任务范围**：Bug/小改动 → 中等特性 → 复杂跨模块，全部要接 → 必须有**分诊（Triage）**先分级再决定流程深度与路由。
- **执行引擎**：真正改代码/跑测试用 **Claude Code / Agent SDK**（headless）。
- **编排器技术栈**：**Python** + SQLite。

## 2. 架构总原则（职责铁律）

这几条是本文档的"宪法"，所有代码评审都以它们为准绳：

1. **核心域纯净**：核心编排上下文中**不得出现任何外部系统概念**（不出现 git / GitLab / 飞书 / Claude Code 的类型、字段、术语）。核心只认领域概念（WorkItem、Gate、Artifact、Verdict…）。
2. **一切外部皆 ACL**：与外部系统/AI 的交互一律封装为**防腐层（Anti-Corruption Layer）适配器**，负责"外部 ↔ 领域语言"的双向翻译。核心通过**端口（Port）**依赖 ACL，而非依赖具体实现。
3. **失败翻译前置**：外部异常在 ACL 边界翻译成领域的 `StageOutcome{failureKind}`；核心策略只认领域失败类型，不认原始异常/HTTP 码。
4. **产物只进不改（版本化）**：产物按阶段键存为**版本列表**；阶段执行（含回退重跑）只能**追加新版本**，永不修改或删除已存版本。"当前产物" = 该键的最新版本。任一步失败前序成果仍在、续跑不重来；回退重跑（VERIFY→IMPL、REVIEW→DESIGN）天然产生新版本，形成重跑审计轨迹。
5. **人审是一等状态**：门禁触发即挂起为 `WAIT_HUMAN`，由外部审批事件唤醒。无人值守 = 关掉该门禁开关，核心逻辑不变。
6. **支撑域承载研发智慧，通用域只搬运**：Intake/Solution 产出领域产物（结构化需求、方案、验收标准）；通用域（Workspace/Execution/Verification/Delivery/Collaboration）不含业务决策。
7. **一切失败终将收敛**：所有重试/回退都有硬上限，无任何无限打转路径；最坏结果永远是"干净地 `FAILED` 并通知人"。

## 3. 统一语言（Ubiquitous Language）

代码、文档、沟通统一使用下列词汇，禁止同义词漂移。

| 中文 | 英文 | 含义 |
|------|------|------|
| 研发任务 | **WorkItem** | 贯穿全流程的核心聚合，一个待完成的研发工作 |
| 需求 | Requirement | 人提出的原始诉求（值对象，结构化后进入 WorkItem） |
| 分诊 | Triage | 给 WorkItem 分级并决定流程深度、工作区模式、路由 |
| 上下文 | Context | 为完成任务收集到的代码/文档/历史知识 |
| 方案 | DesignProposal | 怎么改的设计说明 |
| 评审 | Review | 对方案的审查（AI 自审 / 人审） |
| 验收标准 | AcceptanceCriteria | 判定"做完了"的可检验清单 |
| 验收 | Verification | 按标准跑测试/lint/构建得出结论 |
| 交付 | Delivery | 建分支、push、开 MR、（后续）编排合并 |
| 工作区 | Workspace | mirror 缓存 + 从中拉出的 worktree + 分支 |
| 门禁 | Gate | "此处是否需人确认"的判定点 |
| 门禁点 | GatePoint | 具体门禁位置：REVIEW_GATE、MERGE_GATE |
| 人审挂起 | HumanGate / WAIT_HUMAN | 因门禁而挂起、等人拍板的状态 |
| 自动化旋钮 | AutonomyDial | 每类任务·每仓库对门禁的开关配置 |
| 产物 | Artifact | 某阶段追加到 WorkItem 上、只进不改的结果 |
| 阶段结果 | StageOutcome | 一次阶段执行的领域结果，含成功产物或 failureKind |
| 失败类型 | FailureKind | transient（可重试）/ logic（有限重试或回退）/ fatal（退人） |

## 4. 限界上下文与子域分类

```
                    ┌─────────────────────────────────┐
   ┌── 支撑 ──┐     │        核心域 (Core)             │    ┌── 通用 (集成/ACL) ──┐
   │ 需求接入 │────►│        编排 Orchestration        │◄──►│ 工作区 Workspace     │ (git worktree/mirror)
   │ Intake   │     │  · WorkItem 聚合 + 生命周期状态机 │    │ 交付 Delivery        │ (GitLab MR/pipeline)
   └──────────┘     │  · 分诊路由 TriagePolicy          │    │ 协作 Collaboration   │ (飞书 通知/审批)
   ┌──────────┐     │  · 门禁旋钮 GatePolicy            │◄──►│ 执行 Execution       │ (Claude Code runner)
   │ 方案与评审│────►│  · 转移/重试/回退 Rules           │    │ 验收 Verification    │ (测试/lint/构建 跑取)
   │ Solution │     │                                  │    │ 可观测 Observability │ (trace/日志/看板)
   └──────────┘     └─────────────────────────────────┘    └─────────────────────┘
```

**核心洞察**：本平台核心域异常地"薄"——真正差异化、值得精心建模的只有**编排策略**（什么状态、何时设门禁、按分诊怎么路由、失败怎么重试/回退）。其余几乎所有上下文，本质都是对某个外部能力的 ACL。这直接推导出第 2 节的职责铁律。

| 上下文 | 子域类型 | 一句话职责 |
|--------|----------|-----------|
| 编排 Orchestration | **核心** | 持有 WorkItem 生命周期与全部编排策略；唯一含业务决策的地方 |
| 需求接入 Intake | 支撑 | 把人类原始诉求翻译成结构化 Requirement（发布语言） |
| 方案与评审 Solution | 支撑 | 产出 DesignProposal / Review 结论 / AcceptanceCriteria |
| 工作区 Workspace | 通用 | git mirror 缓存与 worktree/分支的准备与清理（git 的 ACL） |
| 执行 Execution | 通用 | 拉起 Claude Code headless 会话完成编码/检索（Claude 的 ACL） |
| 验收 Verification | 通用 | 在工作区跑测试/lint/构建并给出 Verdict（工具链的 ACL） |
| 交付 Delivery | 通用 | 分支/push/MR/（后续）合并（GitLab 的 ACL） |
| 协作 Collaboration | 通用 | 飞书通知/卡片/审批的收发（飞书的 ACL） |
| 可观测 Observability | 通用 | 订阅领域事件，产出 trace/日志/成本看板 |

> 说明：概念上 9 个上下文；**实现时**可物理合并模块（如 Context/Design/Review/Execution 均由"AI 智能体端口"背书，可共用一族适配器），但**逻辑职责与端口契约保持独立**，以支撑后续按上下文独立加深。

## 5. 上下文映射与集成模式

整体为**六边形架构（Ports & Adapters）**：核心编排域在中心，定义端口；其余上下文实现端口。

```
                Intake ──(Customer/Supplier, 发布语言: 结构化 Requirement)──►┐
              Solution ──(Customer/Supplier, 发布语言: 方案/验收标准)────────►│
                                                                            ▼
                                                ┌────────────────────────────────────┐
   Observability ◄──(订阅领域事件)────────────── │        核心域 · 编排 Orchestration     │
   Collaboration ◄──(订阅领域事件: 通知/审批)──── │  定义出站端口(领域语言, 不含外部概念)   │
                                                └───┬────────┬────────┬────────┬──────┘
                                    每个出站端口由一个 ACL 适配器实现(外部↔领域翻译)
                                        ▼        ▼        ▼        ▼
                                   Workspace  Execution  Verification  Delivery
```

**集成契约：**

- **核心 → 通用**：核心用领域语言定义**出站端口**；通用上下文提供 **ACL 适配器**实现之。核心永不 import 外部 SDK 类型。
- **上游支撑 → 核心**：Customer/Supplier；经稳定的**发布语言 schema**（Requirement/DesignProposal/AcceptanceCriteria）供给，schema 变更需版本化。
- **核心 → 下游订阅者（Observability/Collaboration）**：核心发布**领域事件**，下游订阅消费；核心不知道谁在听（发布订阅解耦）。因此"HumanApprovalRequested → 飞书发审批卡片""WorkItemFailed → 飞书通知"都在 Collaboration 侧对事件的反应，核心零飞书概念。

## 6. 战术模型 · 核心编排上下文

### 6.1 聚合根：WorkItem

WorkItem 是唯一聚合根，也是一致性边界——整条流水线按阶段原子推进。

字段：
```
WorkItem
  id            : WorkItemId
  type          : TaskType            # 分诊得出
  repoRef       : RepoRef             # 逻辑仓库标识, 不含 GitLab 具体字段
  state         : WorkflowState
  requirement   : Requirement         # 来自 Intake 的结构化产物
  artifact_versions : dict[str, list[Artifact]]  # 按阶段键的版本列表, 只追加不改
                                        # 便捷读取: artifacts 属性取每键最新版, current_artifact(key) 取当前
  autonomyDial  : AutonomyDial         # 适用的门禁开关快照
  history       : [StateTransition]   # 转移与事件审计
  retryLedger   : RetryLedger         # 各阶段/回退环的计数
  cost          : Cost                # 累计 token 成本(仅记录)
  createdAt / updatedAt
```

**聚合不变式（由聚合自身守护）：**
- 产物版本化只进不改：`add_artifact` 向该键的版本列表**追加**新版本，永不修改/删除已存版本；`current_artifact(key)` 取最新版本。
- 状态转移必须为合法转移（非法转移被拒绝）。
- 任一重试/回退计数越界 → 强制转 `FAILED`。
- 处于 `WAIT_HUMAN` 时，非经对应 GatePoint 的 approval 事件不得推进。

### 6.2 值对象

| 值对象 | 说明 |
|--------|------|
| `WorkItemId` | 标识 |
| `TaskType` | SmallChange \| MediumFeature \| ComplexFeature（可扩展） |
| `WorkflowState` | INTAKE, TRIAGE, CONTEXT, DESIGN, REVIEW, IMPL, ACCEPT, VERIFY, SUBMIT_MR, DONE, WAIT_HUMAN, FAILED |
| `WorkspaceMode` | WORKTREE \| CLONE \| CREATE |
| `RepoRef` | 逻辑仓库引用（名称/ID），无 GitLab 专有字段 |
| `Requirement` | {goal, targetRepo, acceptanceHints, rawText} |
| `Artifact` 家族 | Intake/Triage/Context/Design/Review/Impl/Acceptance/Verification/Delivery 各一型 |
| `Verdict` | passed + reasons |
| `GatePoint` | REVIEW_GATE \| MERGE_GATE |
| `GateDecision` | {needsHuman, reason} |
| `AutonomyDial` | (taskType, repo, gatePoint) → auto \| human |
| `StageOutcome` | 成功(产物) 或 失败(FailureKind + 摘要) |
| `FailureKind` | transient \| logic \| fatal |
| `RetryLedger` | 各阶段与 VERIFY→IMPL 环的计数 |
| `Cost` | 累计成本（仅记录） |

### 6.3 领域事件（发布语言）

`WorkItemCreated / WorkItemTriaged / ContextGathered / DesignProposed / ReviewApproved / ReviewRejected / HumanApprovalRequested / HumanApprovalGranted / HumanApprovalDenied / ImplementationCompleted / VerificationPassed / VerificationFailed / MRSubmitted / WorkItemSuspended / WorkItemCompleted / WorkItemFailed`

每个事件携带 WorkItemId + 必要上下文。Observability 全量订阅；Collaboration 订阅需要通知/审批的事件。

### 6.4 领域服务（纯策略，零 I/O）

| 领域服务 | 输入 → 输出 |
|----------|-------------|
| `TriagePolicy` | Requirement + 仓库存在性 → TaskType + WorkspaceMode + 路由 |
| `GatePolicy` | WorkItem + GatePoint + AutonomyDial → GateDecision（自动化旋钮的落点） |
| `TransitionRules` | 当前 WorkflowState + StageOutcome → 下一 WorkflowState（含重试/回退判定） |
| `RetryPolicy` | FailureKind + RetryLedger → {重试(退避) \| 回退 \| 升级退人} |

### 6.5 端口（六边形边界）

**入站端口（driving）**：`CreateWorkItem`（trigger/Intake）、`AdvanceWorkItem`（worker）、`ResumeWorkItem`（审批回调）。

**出站端口（driven，领域语言定义，由 ACL 实现）**：
| 端口 | 契约（领域语言） | 由谁实现 |
|------|------------------|----------|
| `WorkItemRepository` | 持久化/加载/捞可推进 WorkItem | SQLite 适配器 |
| `WorkspacePort` | provision(workItem, mode)→WorkspaceHandle；cleanup(handle) | Workspace(git ACL) |
| `ContextPort` | gather(workItem, workspace)→ContextArtifact | Execution(Claude ACL) |
| `DesignPort` | propose(workItem, context)→DesignArtifact | Solution/Execution |
| `ReviewPort` | review(workItem, design)→ReviewArtifact | Solution/Execution |
| `ExecutionPort` | implement(workItem, design, workspace)→ImplArtifact | Execution(Claude ACL) |
| `VerificationPort` | verify(workItem, criteria, workspace)→VerificationArtifact | Verification(工具链 ACL) |
| `DeliveryPort` | submit(workItem, workspace)→DeliveryArtifact；(后续) merge | Delivery(GitLab ACL) |
| `EventPublisher` | publish(domainEvent) | 事件总线；Collaboration/Observability 订阅 |

> 应用层的"阶段处理器（handler）"= 协调出站端口 + 领域服务 + 变更聚合 + 持久化的应用服务。"引擎"= 反复取可推进 WorkItem、应用 TransitionRules 推进聚合的应用层循环。

## 7. 职责规范（每上下文：拥有什么 / 禁止什么）

| 上下文 | 拥有（Owns） | 禁止（Must NOT） | 与核心的集成 |
|--------|--------------|------------------|--------------|
| 编排 Orchestration | WorkItem 聚合、全部领域服务/策略、状态机、端口定义、领域事件 | 出现任何外部 SDK 概念；直接做 I/O | — |
| Intake | Requirement 结构化逻辑 | 决定怎么改代码/是否合并 | 上游 Customer/Supplier，供发布语言 |
| Solution | 方案/评审/验收标准的生成逻辑 | 直接改仓库、提 MR | 上游 Customer/Supplier |
| Workspace | mirror 缓存、worktree/分支准备与清理 | 含业务决策；感知任务语义 | 实现 `WorkspacePort` |
| Execution | Claude Code 会话生命周期、prompt 组装、产物抽取 | 决定门禁/状态流转 | 实现 `Context/Design/Review/ExecutionPort` |
| Verification | 跑测试/lint/构建、汇总 Verdict | 决定失败后怎么办（那是 RetryPolicy） | 实现 `VerificationPort` |
| Delivery | 分支/push/MR/合并的 GitLab 操作、幂等护栏 | 决定是否需要人审 | 实现 `DeliveryPort` |
| Collaboration | 飞书通知/卡片/审批收发、审批→ResumeWorkItem | 决定门禁策略 | 订阅事件 + 调 `ResumeWorkItem` 入站端口 |
| Observability | trace/日志/成本聚合与看板 | 影响流转 | 订阅事件（只读） |

## 8. 演进路线（本模型如何指导逐切片迭代）

模型一次立好，实现逐切片加深。每个切片是"在既定端口/上下文上填充或加深实现"，不改边界。

- **切片 1（当前 spec 范围）**：SmallChange 任务的端到端薄垂直线。全部端口给出**最小实现**：Intake 极简解析、Triage 只判 small、Solution 极简方案、Execution/Verification/Delivery/Collaboration 打通闭环。门禁 REVIEW_GATE、MERGE_GATE 默认开（挂起等人）。
- **切片 2**：加深 Triage（可靠分级 + 路由到不同流程深度）与 MediumFeature 的 Solution 重流程（正式方案 + AI/人评审）。
- **切片 3**：ComplexFeature 跨模块支持；更强 Context（跨仓/历史检索）。
- **切片 4**：按信任梯度放开 AutonomyDial（逐仓库/逐任务类型关门禁），直至无人值守自动合并。
- **横向**：Observability 看板、并发调度（worker 多实例 + WorkItemRepository 领取锁）随需加入，均不触碰核心边界。

## 9. 一致性校准（与 vertical-slice spec 的映射）

spec 是本文档在"切片 1"范围内的实现级细化，须符合本文档。术语映射：

| spec 用语 | 本文档（权威） |
|-----------|----------------|
| Task | **WorkItem**（聚合根） |
| Engine | 应用层：跑 `TransitionRules` 推进聚合的循环 |
| Handlers（九阶段） | 应用服务：协调出站端口 + 领域服务 |
| Adapters（Feishu/GitLab/ClaudeCodeRunner） | **ACL 适配器**，实现对应出站端口 |
| Store | `WorkItemRepository` 端口 + SQLite 适配器 |
| Gate 控制器 | `GatePolicy` 领域服务 + `AutonomyDial` 值对象 |
| 工作区准备（3 模式） | `WorkspacePort` + Workspace 上下文 |
| 失败分类 | ACL 边界翻译为 `StageOutcome.failureKind` |

冲突时以**本文档为准**；spec 已据此更新（见 spec 顶部"架构对齐"小节）。
