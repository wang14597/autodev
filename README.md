# AutoDev — AI 研发工作流编排平台

**一句话定位**：内部自用的无人值守 AI 研发工作流编排器。集成 GitLab + Feishu/Lark，用 Claude Code 执行开发任务，通过配置化"自动化旋钮"按需放开人工审批。

## 背景与目标

研发团队的标准工作流——需求收集、代码上下文、方案设计、方案评审、编码实现、验收测试、提交 MR、等待合并——通常需要大量重复、机械的工作。**AutoDev 的目标是让这些工作都可以由 AI 自动化、规模化、高效化完成**。

### 核心约束与目标

- **面向对象**：内部团队自用工具，优先落地、够用、快见效
- **集成体系**：代码托管在 **GitLab**（MR 与 pipeline）；需求、审批、通知在 **Feishu / Lark**
- **自动化策略**：架构按"全自动无人值守"设计，投产按"信任梯度"放开
  - 每类任务、每个仓库可独立配置"自动化旋钮"（AutonomyDial），决定是否需人工确认
  - 初期在低风险任务上启用，用真实数据积累信任后逐步放开
- **执行引擎**：真正改代码、跑测试的部分使用 **Claude Code / Agent SDK**（headless 会话）
- **编排技术栈**：**Python 3.11+** + SQLite

## 架构一览

AutoDev 采用**六边形架构（Ports & Adapters）**，遵循领域驱动设计（DDD）原则。

```
┌─────────────────────────────────────────────────────────────┐
│                   核心域：编排 Orchestration                  │
│                 （WorkItem 状态机 + 9 阶段流转）             │
│                  · 支撑域：需求接入、方案评审                  │
│             · 出站端口：9 个 ACL 适配器实现的接口            │
└─────────────┬───────────────────────────────────────────────┘
      │ 持久化 │ 工作区准备 │ 智能体执行 │ 验证 │ 交付 │ 通知
      ▼       ▼           ▼            ▼      ▼      ▼
    SQLite  git mirror  Claude Code   测试   GitLab  Feishu
    仓储    & worktree   headless    lint    MR      审批
```

### 架构要点

1. **核心域纯净**：domain/ 内不含任何外部系统概念（git、GitLab、飞书、Claude），只使用领域语言（WorkItem、Artifact、Gate 等）
2. **一切外部皆 ACL**：与外部系统的交互通过"防腐层"（Anti-Corruption Layer）适配器翻译，核心通过端口协议依赖抽象，不依赖具体实现
3. **产物版本化**：阶段产物只进不改，所有版本以列表形式保存，支持失败回退时追加新版本
4. **轻量状态机**：显式的工作流状态转移、持久化、失败重试、人工审批挂起点等机制
5. **失败分类**：外部异常在 ACL 边界翻译为领域的失败类型（transient/logic/fatal），支持自动重试与人工介入

### 详见文档

- **架构基准**：[docs/architecture/2026-07-15-strategic-direction-and-domain-model.md](docs/architecture/2026-07-15-strategic-direction-and-domain-model.md) — 完整的战略方向、领域模型、限界上下文、职责铁律
- **垂直线设计**：[docs/superpowers/specs/2026-07-15-autodev-vertical-slice-design.md](docs/superpowers/specs/2026-07-15-autodev-vertical-slice-design.md) — 第一个垂直切片的实现设计
- **实现计划**：[docs/superpowers/plans/2026-07-15-autodev-slice1-walking-skeleton.md](docs/superpowers/plans/2026-07-15-autodev-slice1-walking-skeleton.md) — 行走骨架的任务分解与验收标准

## 仓库结构

```
autodev/
├── src/autodev/                    # 主程序
│   ├── domain/                     # 核心编排域（99% 的业务逻辑）
│   │   ├── ids.py                  # WorkItemId 标识符
│   │   ├── enums.py                # 枚举：TaskType、WorkflowState、FailureKind 等
│   │   ├── errors.py               # 领域异常（InvariantError 等）
│   │   ├── value_objects.py        # Requirement、AutonomyDial、RepoRef 等值对象
│   │   ├── artifacts.py            # 9 个阶段产物（TriageArtifact...DeliveryArtifact）
│   │   ├── events.py               # 领域事件（WorkItemTriaged、ReviewApproved 等）
│   │   ├── work_item.py            # WorkItem 聚合根 + 状态不变式
│   │   ├── policies.py             # TriagePolicy、GatePolicy、TransitionRules、RetryPolicy
│   │   └── ports.py                # 出站端口协议（Protocol）定义
│   │
│   ├── application/                # 应用层（协调端口 + 执行流转）
│   │   ├── context.py              # StageContext（端口和策略聚合）
│   │   ├── engine.py               # 状态机引擎（fetch → push → handle loop）
│   │   ├── handlers/               # 9 个阶段处理器
│   │   │   ├── handler.py          # 处理器基类
│   │   │   ├── intake.py           # 需求接入
│   │   │   ├── triage.py           # 分诊分级
│   │   │   ├── context_gather.py   # 上下文收集
│   │   │   ├── design.py           # 方案设计
│   │   │   ├── review.py           # 方案评审
│   │   │   ├── impl.py             # 编码实现
│   │   │   ├── accept_criteria.py  # 验收标准
│   │   │   ├── verify.py           # 验收测试
│   │   │   └── submit_mr.py        # 提交 MR
│   │   └── entrypoints.py          # API：create_work_item / resume_work_item
│   │
│   └── adapters/                   # 适配器（外部系统 ACL）
│       ├── repo_sqlite.py          # WorkItemRepository 的 SQLite 实现
│       └── event_memory.py         # EventPublisher 的内存实现
│
├── tests/                          # 测试
│   ├── unit/                       # 单元测试（domain/application）
│   └── e2e/                        # 端到端测试
│
├── docs/
│   ├── architecture/               # 架构和战略文档
│   └── superpowers/                # 切片计划与设计文档
│
├── pyproject.toml                  # 项目配置与依赖声明
└── README.md                       # 本文件
```

### 职责速览

| 模块 | 职责 |
|------|------|
| **domain/** | 领域聚合、状态机、策略、端口定义、事件。完全不依赖外部系统。 |
| **application/** | 应用服务：协调端口 + 策略推进聚合，持久化结果。 |
| **adapters/** | ACL 适配器：翻译外部系统概念 ↔ 领域语言。存储、事件总线等实现。 |
| **tests/** | 单元测试（domain/application）+ 端到端集成测试。 |

## 快速开始

### 前置要求
- Python 3.11+
- Git
- 可选：GNU Make（用于快速命令）

### 安装与测试

```bash
# 创建虚拟环境
python3 -m venv venv
. venv/bin/activate

# 安装（包含开发依赖）
pip install -e '.[dev]'

# 跑全部测试
pytest -q
```

预期输出：
```
................................................... [100%]
48 passed in 0.12s
```

### 主要命令

```bash
# 跑所有单元测试
pytest -q

# 跑特定测试模块
pytest tests/unit/domain/test_work_item.py -v

# 跑端到端测试
pytest tests/e2e/ -v

# 带覆盖率报告
pytest --cov=src/autodev --cov-report=term-missing tests/

# 类型检查（后续支持）
mypy src

# 代码格式与 lint（后续支持）
ruff check .
```

## 当前状态

### 已完成（切片 1：行走骨架）

✅ **领域模型与核心编排**
- WorkItem 聚合根及其完整生命周期
- 11 个工作流状态（INTAKE → DONE，含 WAIT_HUMAN、FAILED、回退）
- 9 阶段处理器（需求→分诊→上下文→设计→评审→实现→验收标准→验收→提 MR）

✅ **领域服务与策略**
- TriagePolicy：任务分类（SmallChange）与工作区模式选择
- GatePolicy：门禁判定（REVIEW_GATE、MERGE_GATE）与自动化旋钮（AutonomyDial）
- TransitionRules：状态转移规则与合法性校验
- RetryPolicy：失败重试与回退决策

✅ **出站端口**
- 9 个端口协议已定义：WorkItemRepository、WorkspacePort、ContextPort、DesignPort、ReviewPort、ExecutionPort、VerificationPort、DeliveryPort、EventPublisher
- **2 个端口已真实实现**：
  - WorkItemRepository → SQLite 适配器（持久化/查询）
  - EventPublisher → 内存事件总线
- **7 个端口当前为假实现**（mock/stub），真实 ACL 见下方"计划中"

✅ **测试覆盖**
- **48 个测试全部通过**
- 涵盖：值对象、聚合不变式、状态转移、重试政策、阶段处理器、端到端流程

### 计划中（后续切片）

| 切片 | 重点 | 计划时间 |
|------|------|---------|
| **切片 2：真实 ACL + E2E 冒烟** | 实现 Workspace（git mirror/worktree）、Execution（Claude Code runner）、Verification（测试/lint/构建）、Delivery（GitLab MR）、Collaboration（Feishu 通知/审批）的真实适配器；端到端冒烟测试 SmallChange 完整闭环 | ▢ |
| **切片 3：中/复杂特性重流程** | 支持 MediumFeature / ComplexFeature 任务类型；加深 Triage（多维度路由）、Solution（详细方案+多轮评审）、Context（跨仓/历史检索）；更强的 AI 智能体能力 | ▢ |
| **切片 4：信任梯度自动合并** | 按任务类型/仓库的精细 AutonomyDial 配置；逐步放开 MERGE_GATE，实现全自动无人值守合并；日志/看板支持 | ▢ |
| **横向：可观测 + 并发 + 安全** | 完整 trace/日志/成本 dashboard；多 worker 并发处理；权限模型与凭证管理；AI 执行沙箱与 prompt 注入防护 | ▢ |

### 端口实现进度

```
出站端口（共 9 个）：

✓ WorkItemRepository        → SQLite 适配器
✓ EventPublisher            → 内存事件总线

✗ WorkspacePort           → 假实现（阶段 2 真实化）
✗ ContextPort             → 假实现（阶段 2 真实化）
✗ DesignPort              → 假实现（阶段 2 真实化）
✗ ReviewPort              → 假实现（阶段 2 真实化）
✗ ExecutionPort           → 假实现（阶段 2 真实化）
✗ VerificationPort        → 假实现（阶段 2 真实化）
✗ DeliveryPort            → 假实现（阶段 2 真实化）
```

## 文档索引

### 架构与设计

- **[战略方向与领域模型](docs/architecture/2026-07-15-strategic-direction-and-domain-model.md)**（2026-07-15）
  - 核心定位、9 个限界上下文、职责铁律、统一语言、DDD 战术模型
  - **阅读顺序**：第一份必读文档

- **[垂直线设计](docs/superpowers/specs/2026-07-15-autodev-vertical-slice-design.md)**（2026-07-15）
  - 第一个垂直切片（SmallChange 任务）的实现设计
  - 平台拆解、架构、9 个阶段的具体设计
  - **阅读顺序**：了解 spec 后阅读

- **[ADR 架构决策记录](docs/adr/README.md)**（规划中）
  - 轻量状态机选型、产物版本化、领域语言中性化

### 实现计划

- **[项目基线](docs/superpowers/plans/2026-07-15-project-baseline.md)**（2026-07-15）
  - 5 个任务：README + ROADMAP、架构图、ADR、治理文件、质量门禁
  - 本轮迭代的"一次性"工程资产

- **[行走骨架计划](docs/superpowers/plans/2026-07-15-autodev-slice1-walking-skeleton.md)**（2026-07-15）
  - 13 个开发任务（已全部完成），从领域模型到 E2E 测试
  - 含每个任务的验收标准

### 路线图

- **[ROADMAP.md](ROADMAP.md)**
  - 全部 4 个垂直切片的范围、依赖、时间线
  - 横向关切面（可观测、并发、安全）的演进

## 常见问题

**Q：为什么不用现成的工作流引擎（Temporal/Prefect/等）？**
A：切片 1 的目标是快速见效与精准贴合"AI 阶段 + 人工审批挂起"的编排模式。轻量状态机足以支撑核心逻辑，必要时后续可扩展。

**Q：核心域为什么禁止外部 SDK？**
A：这是职责铁律#1（核心域纯净）的落地。不含 git/GitLab/飞书 概念的纯领域模型，才能保证核心逻辑的稳定性、可测试性、与外部系统解耦。所有外部交互通过 ACL 适配器翻译。

**Q：如何添加新的任务类型（MediumFeature/ComplexFeature）？**
A：修改 TaskType 枚举 → 扩展 TriagePolicy 与 Solution 的处理器 → 添加对应测试。见《战略方向与领域模型》第 8 节"演进路线"。

**Q：为什么要版本化产物？**
A：支持失败时的精确回退与重跑审计。一个阶段失败后，可以回退到前序阶段修复后重新推进，新产物追加到版本列表，完整保留执行历史。

## 贡献指南

参见 `CONTRIBUTING.md`（规划中）。核心要求：
- 遵守职责铁律（domain/ 不含外部 SDK；外部交互走 ACL）
- 统一语言：WorkItem、Artifact、Gate、AutonomyDial 等术语禁止同义词
- 产物只进不改：add_artifact 永不覆盖已存版本
- 每次修改必须 `pytest -q` 全绿（保持 48+ 测试）

## 许可证

内部专有。保留所有权利。

---

**最后更新**：2026-07-15  
**项目负责人**：AutoDev Team  
**反馈/问题**：见项目 GitLab issues
