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
│             · 出站端口：11 个 ACL 适配器实现的接口           │
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
│   │   ├── artifacts.py            # <!-- fact:artifacts -->8 个阶段产物（TriageArtifact...DeliveryArtifact）
│   │   ├── events.py               # <!-- fact:events -->4 个领域事件（WorkItemCreated、HumanApprovalRequested、WorkItemCompleted、WorkItemFailed）
│   │   ├── work_item.py            # WorkItem 聚合根 + 状态不变式
│   │   ├── policies.py             # GatePolicy、AutonomyPolicy、TransitionRules、RetryPolicy
│   │   └── ports.py                # 出站端口协议（Protocol）定义
│   │
│   ├── application/                # 应用层（协调端口 + 执行流转）
│   │   ├── context.py              # StageContext（端口和策略聚合）
│   │   ├── engine.py               # 状态机引擎（fetch → push → handle loop）
│   │   ├── handlers.py             # 9 个阶段处理器（handle_intake、handle_triage、handle_context、handle_design、handle_review、handle_impl、handle_accept、handle_verify、handle_submit_mr）
│   │   └── entrypoints.py          # API：create_work_item / resume_work_item
│   │
│   └── adapters/                   # 适配器（外部系统 ACL）
│       ├── sqlite_repository.py    # WorkItemRepository 的 SQLite 实现
│       ├── memory_repository.py    # 内存存储实现
│       └── event_bus.py            # EventPublisher 实现
│
├── tests/                          # 测试
│   ├── domain/                     # 领域模型单元测试
│   │   ├── test_enums.py           # 枚举测试
│   │   ├── test_outcome.py         # Outcome 值对象测试
│   │   ├── test_policies.py        # 策略测试
│   │   ├── test_value_objects.py   # 值对象测试
│   │   └── test_work_item.py       # WorkItem 聚合根测试
│   ├── application/                # 应用层单元测试
│   │   ├── test_engine.py          # 状态机引擎测试
│   │   ├── test_entrypoints.py     # API 测试
│   │   ├── test_handlers_back.py   # 后置阶段处理器测试
│   │   └── test_handlers_front.py  # 前置阶段处理器测试
│   ├── adapters/                   # 适配器单元测试
│   │   └── test_sqlite_repository.py # SQLite 存储库测试
│   ├── e2e/                        # 端到端测试
│   │   └── test_walking_skeleton.py # 行走骨架场景测试
│   ├── conftest.py                 # pytest 配置与 fixtures
│   ├── fakes.py                    # 假实现（stub/mock 适配器）
│   ├── test_fakes.py               # 假实现自身的测试
│   └── test_sanity.py              # 健全性检查
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

一次性钩子安装：`pre-commit install --hook-type pre-push`。装好之后，每次 `git push` 前会在本机自动跑一次非阻塞的文档一致性顾问（`scripts/docs_advise.py`；需已连 VPN、本地已登录 Claude Code，环境不可用时打印一行非阻塞提示后继续，绝不阻塞 push）。也可随时手动跑：`python scripts/docs_advise.py`。

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

# 类型检查
mypy src

# 代码 lint（含格式检查）
ruff check .

# 自动格式化
ruff format .
```

详见 `CONTRIBUTING.md` 的 Linter / Type Checker 章节。

### 控制台（前端 + 后端）

平台控制台以领域聚合根 **Project（项目）** 为中心，**两步流程**：先建项目（登记一个 git 仓库或本地路径 + **跟踪分支**（可留空取仓库默认），此时做一次性 setup：`git fetch` 同步远端 + 探测分支）→ 在项目下创建多个工作项（WorkItem，只填需求）。工作项后台自动驱动 需求录入→分诊→上下文收集（真调 Claude）→ 详情页展示完整生命周期与产出的上下文简报；其 worktree 以项目跟踪分支的最新（`origin/<branch>`）为基点。同一项目下的工作项**共享一次性 setup**（不再重复判断分支/拉远程）。点项目「刷新」会重新 `git fetch` 把远端更新同步到本地。导航：项目列表 → 项目详情（其工作项 + 在此新建 + 刷新 + 删除）→ 工作项详情。当前跑到**方案**阶段为止，评审及之后（评审/开发/验收…）标"待建设"，随 F5–F8 接入。工作项的 `autonomy_enabled` 是**节奏开关**：开＝自动挡（连续跑到平台能力边界）；关＝手动挡（只读收集段仍自动跑完，之后每个阶段由你点「推进」走一步）。真调 Claude 需在能访问内网网关的环境（VPN）里运行。

- 后端：`src/autodev/webapp/`（FastAPI），用真实 `Project`/`WorkItem`/SQLite 仓储/`Engine` + F1/F3/分诊/方案适配器；驱动跑 需求录入→分诊→上下文→方案，止于评审。"平台能执行哪些阶段"是**单一真源**（`src/autodev/webapp/drive.py` 的 `IMPLEMENTED_STAGES`），驱动边界、"待建设"标记、「推进」按钮可用性三处共用同一份，扩容时一改三生效。
- 前端：`frontend/`（Vite + React + TypeScript，TanStack Query 轮询，React Router），字体与 Markdown 渲染库本地打包，运行时零公网 CDN。

**生产运行（构建后由后端一体托管）：**

```bash
cd frontend && npm ci && npm run build && cd ..     # 1) 构建前端 → frontend/dist
pip install -e '.[web]'                              # 2) 装后端 Web 依赖
export AUTODEV_HOME="$HOME/.autodev"                 # 项目库/工作项库/上下文结果落地(默认 ~/.autodev)
export ANTHROPIC_BASE_URL="http://<内网网关地址>:<端口>/api"   # 内网网关(需 VPN；实际地址向团队获取)
python -m autodev.webapp                             # 默认 http://127.0.0.1:8000
```

启动后在页面里**新建项目**（填 git 仓库地址或本地 git 仓库目录路径，会自动登记并做一次性 setup），再在项目下创建工作项。可选 `AUTODEV_REPO_MAP`（JSON）用于预置仓库映射。未构建 `frontend/dist` 时，后端返回占位页（提示先构建），API 仍可用。

**前端开发（热更新，代理到后端）：** 终端 A `python -m autodev.webapp`；终端 B `cd frontend && npm run dev`（Vite :5173，`/api` 自动代理到 :8000）。

前端门禁（`frontend/` 下）：`npm run typecheck`、`npm run lint`、`npm run test`、`npm run build`、`npm run format:check`。前置：Node ≥ 20、npm（内网需可访问 registry 或内部镜像）。可选环境变量：`AUTODEV_MIRROR_DIR`、`AUTODEV_WORKSPACES_DIR`、`AUTODEV_WEB_HOST`、`AUTODEV_WEB_PORT`、`AUTODEV_FRONTEND_DIST`。

## 当前状态

### 已完成（切片 1：行走骨架）

✅ **领域模型与核心编排**
- WorkItem 聚合根及其完整生命周期
- <!-- fact:workflow_states -->12 个工作流状态（INTAKE → DONE，含 WAIT_HUMAN、FAILED、回退）
- 9 阶段处理器（需求→分诊→上下文→设计→评审→实现→验收标准→验收→提 MR）

✅ **领域服务与策略**
- 分诊：任务分类 / 风险 / 意图（是否仅咨询）经 `TriagePort` 交由 LLM（`LlmTriageAdapter`，直连 Messages API/Opus 4.8）判定；核心域只消费 `TriageSignal`，不含分诊规则
- AutonomyPolicy：上下文后决策（`autonomy_enabled` 关→挂起 CONTEXT_GATE 交用户；开+咨询→仅收集完成；开+落地→继续），安全优先（分诊不可用/低置信度一律先挂起）
- GatePolicy：风险感知门禁判定（REVIEW_GATE、MERGE_GATE、CONTEXT_GATE），OR-单调放行 + 自动化旋钮（AutonomyDial）
- TransitionRules：状态转移规则与合法性校验
- RetryPolicy：失败重试与回退决策

✅ **出站端口**
- <!-- fact:ports -->11 个端口协议已定义：WorkItemRepository、ProjectRepository、WorkspacePort、TriagePort、ContextPort、DesignPort、ReviewPort、ExecutionPort、VerificationPort、DeliveryPort、EventPublisher
- **7 个端口已真实实现**：
  - WorkItemRepository → SQLite 适配器（持久化/查询）
  - ProjectRepository → SQLite 适配器（项目聚合持久化）
  - EventPublisher → 内存事件总线
  - TriagePort → LlmTriageAdapter（直连 Messages API/Opus 4.8，强制 tool_use 结构化输出）
  - WorkspacePort → GitWorkspaceAdapter（git bare mirror + worktree，F1）
  - ContextPort → ClaudeContextAdapter（Claude Code 两遍收集→复核，F3）
  - DesignPort → ClaudeDesignAdapter（Claude Code 只读单遍产出方案 Markdown，F4）
- **4 个端口当前为假实现**（mock/stub）：Review/Execution/Verification/Delivery，真实 ACL 见下方"计划中"
- 另有驱动侧适配器：项目控制台（前端 `frontend/` + 后端 `src/autodev/webapp/`），以 Project 为中心驱动工作项走 需求录入→分诊→上下文→方案；节奏由 `autonomy_enabled` 决定（自动挡连续跑到能力边界，手动挡在收集段之后每阶段等人点「推进」），风险门禁照常挂起为 `WAIT_HUMAN` 交人审

✅ **测试覆盖**
- **341 个测试全部通过**（另有 3 个 live 用例默认跳过，需 `AUTODEV_LIVE=1` + 可用 claude/内网网关触发）
- 涵盖：值对象、聚合不变式、状态转移、重试政策、分诊/自主策略、阶段处理器、LLM 分诊契约、端到端流程

### 计划中（后续切片）

| 切片 | 重点 | 计划时间 |
|------|------|---------|
| **切片 2：真实 ACL + E2E 冒烟** | 实现 Workspace（git mirror/worktree）、Context/Design/Review（Claude Code runner）、Execution（Claude Code runner）、Verification（测试/lint/构建）、Delivery（GitLab MR）7 个端口的真实适配器；集成 Feishu/Lark 通知与审批（Collaboration 限界上下文，非独立端口）；端到端冒烟测试 SmallChange 完整闭环 | ▢ |
| **切片 3：中/复杂特性重流程** | 支持 MediumFeature / ComplexFeature 任务类型；加深 Triage（多维度路由）、Solution（详细方案+多轮评审）、Context（跨仓/历史检索）；更强的 AI 智能体能力 | ▢ |
| **切片 4：信任梯度自动合并** | 按任务类型/仓库的精细 AutonomyDial 配置；逐步放开 MERGE_GATE，实现全自动无人值守合并；日志/看板支持 | ▢ |
| **横向：可观测 + 并发 + 安全** | 完整 trace/日志/成本 dashboard；多 worker 并发处理；权限模型与凭证管理；AI 执行沙箱与 prompt 注入防护 | ▢ |

### 端口实现进度

```
出站端口（共 <!-- fact:ports -->11 个）：

✓ WorkItemRepository        → SQLite 适配器
✓ ProjectRepository         → SQLite 适配器（项目聚合）
✓ EventPublisher            → 内存事件总线

✓ TriagePort              → LlmTriageAdapter（直连 Messages API/Opus 4.8）
✓ WorkspacePort           → GitWorkspaceAdapter（git mirror + worktree，F1）
✓ ContextPort             → ClaudeContextAdapter（Claude Code 收集→复核，F3）
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

- **[ADR 架构决策记录](docs/adr/README.md)**
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
A：修改 TaskType 枚举 → 更新分诊提示词（`LlmTriageAdapter`）以覆盖新类型 → 扩展 Solution 的处理器 → 添加对应测试。见《战略方向与领域模型》第 8 节"演进路线"。

**Q：为什么要版本化产物？**
A：支持失败时的精确回退与重跑审计。一个阶段失败后，可以回退到前序阶段修复后重新推进，新产物追加到版本列表，完整保留执行历史。

## 贡献指南

参见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。核心要求：
- 遵守职责铁律（domain/ 不含外部 SDK；外部交互走 ACL）
- 统一语言：WorkItem、Artifact、Gate、AutonomyDial 等术语禁止同义词
- 产物只进不改：add_artifact 永不覆盖已存版本
- 每次修改必须 `pytest -q` 全绿（保持 48+ 测试）

## 许可证

内部专有。保留所有权利。

---

**最后更新**：2026-07-16  
**项目负责人**：AutoDev Team  
**反馈/问题**：见项目 GitHub issues（本仓库托管在 GitHub；平台运行时对接的目标项目才是 GitLab）
