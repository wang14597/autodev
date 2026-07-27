# AutoDev 产品路线图

> **创建**：2026-07-15  
> **最近校准**：2026-07-25（与代码对齐）  
> **状态**：活跃  
> **维护者**：AutoDev Team

## 概览

AutoDev 按垂直切片逐步演进，从"最薄的行走骨架"到"全自动无人值守 AI 编程"。每个切片在既定架构边界内加深实现，不推翻重来。

```
▌┐
▌│ 切片 4：信任梯度自动合并（⇒ 无人值守）        ▢ 未开始
▌├ 切片 3：中/复杂特性重流程 + 强上下文          ▢ 未开始
▌├ 切片 2：真实 ACL + E2E 冒烟                  ◐ 进行中（Workspace/Context 已落地）
▌└ 切片 1：行走骨架                             ✓ 已完成
│
├─→ 控制台 + Project 一等概念（Web 平台外观）    ✓ 已交付
│   （0.1.2 / Unreleased）
└─→ 项目基线：门面文档、架构图、ADR、质量门禁    ✓ 已完成
    （0.1.1）
```

> **文档-代码对齐说明（2026-07-25）**：本 ROADMAP 曾定格在 0.1.1 项目基线。此后代码实质推进了两块：
> ①「控制台 + Project 一等概念」里程碑已交付（见下节）；②切片 2 已启动，7 个假适配器中
> `WorkspacePort`、`ContextPort` 两个真实 ACL 适配器已实现。以 [CHANGELOG](CHANGELOG.md) 的
> `[Unreleased]` 段与本文为当前权威基准。

---

## 项目基线（0.1.1）— ✓ 已完成

**目标**：补齐专业项目必备资产，与功能解耦。

**时间线**：2026-07-15 - 2026-07-16  
**状态**：✓ 已完成  
**依赖**：切片 1 完成（✓ 已满足）

| 任务 | 描述 | 状态 | 负责 |
|------|------|------|------|
| B1 | README + ROADMAP（项目门面） | ✓ 已完成 | — |
| B2 | 架构图（5 张 Mermaid，含系统/限界/状态机/时序/数据模型） | ✓ 已完成 | — |
| B3 | ADR 决策记录（轻量引擎/版本化/中性化） | ✓ 已完成 | — |
| B4 | 协作与治理（CONTRIBUTING/SECURITY/LICENSE/CHANGELOG/PR 模板/CODEOWNERS） | ✓ 已完成 | — |
| B5 | 质量门禁（ruff/mypy/pre-commit/GitHub Actions CI） | ✓ 已完成 | — |

**完成时间**：2026-07-16

**验收标准**：
- ✓ 所有 markdown 内链指向真实文件
- ✓ 无 TODO 占位（除显式"待填"处）
- ✓ 快速开始命令与仓库实际一致
- ✓ 本地 `ruff check` / `mypy src` / `pytest -q` 全部通过

**产出物**：
- `README.md` 一份
- `ROADMAP.md` 一份（本文件）
- `docs/architecture/diagrams.md` 含 5 张图
- `docs/adr/` 含 5 个文件
- `CONTRIBUTING.md` / `SECURITY.md` / `LICENSE` / `CHANGELOG.md` / `.github/pull_request_template.md` / `.github/CODEOWNERS` / `.pre-commit-config.yaml` / `.github/workflows/ci.yml`
- `pyproject.toml` 更新（ruff/mypy 配置）

---

## 控制台 + Project 一等概念（0.1.2 / Unreleased）— ✓ 已交付

**目标**：给平台一张面向用户的操作面(driving adapter)，并引入「项目」作为组织多个工作项的一等聚合，使平台从「库 + 测试」进化为「可点开就用的 Web 控制台」。此里程碑在 ROADMAP 原计划之外补入，为切片 2 的真实闭环提供操作入口。

**时间线**：2026-07-16 - 2026-07-25  
**状态**：✓ 已交付（进行中的 Unreleased 段，尚未打 tag）

**实现范围**：
- ✓ **`Project` 领域聚合**：`ProjectId`、name、仓库来源、跟踪分支(`branch`)、project 级 `AutonomyDial`；配套 `ProjectRepository` 端口（`SqliteProjectRepository` / `InMemoryProjectRepository` 两实现）。`WorkItem` 增 `project_id` 归属、`base_branch`。出站端口由 9 增至 <!-- fact:ports -->11（新增 ProjectRepository）。
- ✓ **Web 后端**（`src/autodev/webapp/`，FastAPI）：项目与工作项 REST API（`GET/POST /api/projects`、项目详情/刷新/删除、项目下建工作项、列分支、切默认分支）；**有界驱动**只自动跑 INTAKE→TRIAGE→CONTEXT 止于 DESIGN；生产托管 `frontend/dist`（SPA 回退 + 目录穿越防护）。
- ✓ **前端控制台**（`frontend/`，Vite + React + TypeScript + TanStack Query + React Router）：以「项目」为中心的两步导航（项目列表 → 项目详情 → 工作项详情），创建项目/工作项、生命周期流水线可视化、上下文简报渲染；字体与 Markdown 库本地打包（运行时零公网 CDN）；antd Select 模糊搜索切换默认分支。
- ✓ **本地仓库直挂 worktree**：项目输入为本地 git 目录时自动登记并 `git worktree add`（共享对象库、秒级、不碰工作目录），登记持久化到 `~/.autodev/repos.json`。
- ✓ **前端质量门禁**：typecheck / oxlint / vitest / build / prettier，接入 GitHub Actions frontend job。

**验收标准**：
- ✓ 后端应用服务 / 视图投影 / 路由均以注入假件单测
- ✓ 前端组件与 hooks 有 vitest 覆盖
- ✓ 未构建前端时回退占位页、API 仍可用

**尚缺（转入切片 2/后续）**：真实浏览器端到端(E2E)冒烟、DESIGN 及之后阶段的真实驱动（当前止于 CONTEXT，DESIGN 起为抛错桩）、Delivery 的 push/开 MR。

---

## 切片 1：行走骨架（SmallChange 端到端）

**✓ 已完成**

**目标**：最薄垂直线：SmallChange（小改动/明确 Bug）任务从创建、分诊、上下文、设计、评审、实现、验收、提 MR 到等待合并的完整闭环。

**实现范围**：
- ✓ 核心编排域（WorkItem 聚合、12 个工作流状态、9 个阶段处理器）
- ✓ 领域服务（TriagePolicy、GatePolicy、TransitionRules、RetryPolicy）
- ✓ 端口协议（9 个出站端口定义）
- ✓ 2 个真实适配器：SQLite 仓储 + 内存事件总线
- ✓ 7 个假适配器（MockWorkspace / MockExecution / 等）
- ✓ 48 个单元 + 端到端测试

**工作流状态**：
```
INTAKE → TRIAGE → CONTEXT → DESIGN → REVIEW → IMPL → ACCEPT → VERIFY → SUBMIT_MR → DONE
  ↑                                     ↓                            ↓
  └─ WAIT_HUMAN ← 人工审批 ────────────┘                            ↓
                                                                   FAILED ← 任意阶段失败
```

**人审门禁**：
- REVIEW_GATE：方案评审后，是否需人确认？
- MERGE_GATE：提 MR 后，是否需人确认合并？
- 配置化决策：AutonomyDial(taskType, repo, gatePoint) → auto | human

**重试与回退**：
- 阶段失败 → RetryPolicy 判定：transient（自动重试，有上限）/ logic（需回退）/ fatal（转人工）
- 支持：VERIFY→IMPL（发现问题改代码）、REVIEW→DESIGN（评审拒绝重新设计）
- 所有重试/回退计数都有硬上限，越界强制转 FAILED

**交付文档**：
- [行走骨架计划](docs/superpowers/plans/2026-07-15-autodev-slice1-walking-skeleton.md)：13 个开发任务
- [垂直线设计](docs/superpowers/specs/2026-07-15-autodev-vertical-slice-design.md)：实现级细化
- [战略方向与领域模型](docs/architecture/2026-07-15-strategic-direction-and-domain-model.md)：架构基准

**版本**：0.1.0  
**完成时间**：2026-07-15

---

## 切片 2：真实 ACL + E2E 冒烟

**◐ 进行中**（Workspace / Context 两个真实适配器已落地，其余 5 个待实现）

**目标**：将 7 个假适配器替换为真实实现，跑通完整的端到端冒烟测试。

**依赖**：切片 1（✓ 已完成）、控制台里程碑（✓ 已交付，提供操作入口）

**适配器进度**：

| 适配器 | 职责 | 当前状态 | 落点 / 计划 |
|--------|------|---------|---------|
| **WorkspacePort** | git mirror 缓存 + worktree/分支准备与清理 | ✅ 真实已实现（`GitWorkspaceAdapter`）**且已接入组合根**（`config.py`），有界驱动的 TRIAGE/CONTEXT 已真实使用 | 本地 git + bare mirror；后续补 push + GitLab 远程 |
| **ContextPort** | 为 WorkItem 收集代码/文档上下文 | ✅ 真实已实现（`ClaudeContextAdapter` + `ClaudeCodeRunner`，含 live 冒烟）且已接入组合根 | 已产出 Markdown 上下文文档，持久化到 `~/.autodev` |
| **DesignPort** | 根据 Requirement + Context 生成 DesignProposal | ⬜ 假 | 真实（复用 `ClaudeCodeRunner`） |
| **ReviewPort** | 对 DesignProposal 做代码评审 | ⬜ 假 | 真实（复用 `ClaudeCodeRunner`） |
| **ExecutionPort** | 按 DesignProposal 编码实现 | ⬜ 假 | 真实（复用 `ClaudeCodeRunner`，需执行沙箱） |
| **VerificationPort** | 跑测试/lint/构建得出 Verdict | ⬜ 假 | 真实（测试框架 + lint + 构建工具集成） |
| **DeliveryPort** | 创建分支、push、开 MR、（后续）编排合并 | ⬜ 假 | 真实（GitLab API） |

**核心工作**：
- ✅ 实现 Workspace ACL：bare mirror 管理、worktree 生命周期（`GitWorkspaceAdapter`，REUSE/FETCH/CREATE 三模式）
- ✅ Claude Code headless runner 基座（`ClaudeCodeRunner`：子进程调 `claude` CLI + 超时/重试 + transient/fatal/logic 失败分类）
- ◐ 复用该基座实现 Design / Review / Execution 三个真实适配器
- ⬜ 把真实 `WorkspacePort` 接入运行主循环，让 DESIGN 及之后阶段真实驱动
- ⬜ 集成验证工具链：pytest / ruff / mypy / 构建脚本
- ⬜ 集成 GitLab API：MR 创建、合并权限、pipeline 状态查询
- ⏸ 集成 Feishu/Lark API：通知卡片、审批流、事件回调 —— **暂不纳入当前规划**（后续再议）

**端到端冒烟测试**：
- 创建一个真实的 SmallChange 需求（从 Feishu 或本地文件）
- 完整推进 9 个阶段，真实改一个开源参考项目
- 验证 MR 最终被创建、草稿分支正确

**Observability 基础**：
- 每个 WorkItem 的完整 trace（所有阶段时间、成本、输出）
- 实时日志输出到 stdout + 文件

**计划时间**：待定  
**预期工作量**：2-3 周

---

## 切片 3：中/复杂特性重流程 + 强上下文

**目标**：支持 MediumFeature / ComplexFeature 任务类型，加深设计与评审流程，更强的上下文检索。

**依赖**：切片 2（真实 ACL 完成）

**实现范围**：

### 任务类型扩展

| 类型 | 特征 | TRIAGE 路由 | 预期耗时 |
|------|------|-----------|---------|
| **SmallChange** | 一个文件、<100 行改动 | 快速路径 | 几分钟 |
| **MediumFeature** | 跨 1-2 个模块、需完整方案 | 标准路径 + 人评审 | 几十分钟 |
| **ComplexFeature** | 跨 3+ 个模块、需 AI + 人多轮设计 | 完整路径 + 高关注度 | 数小时 |

### Solution 上下文加深

**当前**：极简方案生成（一轮）  
**加深**：
- MediumFeature：结构化需求 + 约束条件 + 验收清单 → 详细设计 + 实现步骤
- ComplexFeature：增加 AI + 人工的多轮设计评审（见下）

### Design 与 Review 重流程

```
┌─ AI 初步方案 ──┬─ 人工评审拒绝 ──┬─ 提升约束 ──┐
│                │                │           │
▼                ▼                ▼           │
AI 精化方案 ──► AI 自审 ──► 人工最终评审 ───┴─► 执行
                 ▲
                 └─ 不通过，改约束后重跑 AI
```

### Context 强化

**当前**：相同仓库的相邻文件  
**加深**：
- 跨仓库检索：从相关项目拉取参考代码
- 历史查询：该模块的 commit history / issue 讨论
- 向量化搜索：相似功能的已实现部分
- 文档索引：来自 README / wiki / RFD 的上下文

### 执行沙箱

- Claude Code headless 会话在隔离的目录（git clone 副本）中运行
- 限制：CPU / 内存 / 磁盘 / 网络（仅允许特定源）
- 失败隔离：会话崩溃不影响其他 WorkItem

**计划时间**：待定  
**预期工作量**：3-4 周

---

## 切片 4：信任梯度自动合并

**目标**：按任务类型、仓库精细配置 AutonomyDial，逐步放开 MERGE_GATE，达成"全自动无人值守"合并。

**依赖**：切片 3（多类型、重流程完成）

**实现范围**：

### AutonomyDial 精细化

**当前**：二值（auto | human）  
**加深**：分阶段的多元决策
```
AutonomyDial = {
  "triage.auto":         true,      # 自动分级
  "design.auto":         true,      # 自动设计
  "review.auto":         false,     # 需人评审
  "verify.auto":         true,      # 自动验证
  "merge.auto":          false,     # 需人合并（初期）
  "review.gate":         "all",     # all | owner_only | none
  "merge.gate":          "all",     # all | owner_only | none
  "merge.auto_after_days": 1,       # N 天无异议自动合并
  "safety_checks":       true,      # 强制安全检查（权限、凭证）
}
```

### 信任积累机制

```
初期状态（低信任）：
  merge.gate = "all"（所有 MR 需人）
     ↓ 观察 10 个 SmallChange + 5 个 MediumFeature，0 线上 bug
  过渡状态（中信任）：
  merge.gate = "owner_only"（仅需作者最后确认）
     ↓ 再积累 2 周无事故
  最终状态（高信任）：
  merge.auto = true（MR 自动合并 + 日志审计）
```

### 审计与回滚

- 每个自动合并记录完整的决策链：Requirement → Design → Review → Verdict → Auto-Merge Log
- 合并后若发现问题，可追溯并触发"Rollback + RootCause Analysis"流程
- 恶意需求检测：prompt 注入、权限越界等（与 Security 侧协同）

### 人工再介入

- MERGE_GATE 在信任下降时重新关闭（如发现连续线上 bug）
- 紧急 hotfix 路径：bypass 自动合并，直接人工 merge

**计划时间**：待定  
**预期工作量**：2 周

---

## 横向关切面

### 可观测性（Observability）

**目标**：完整的 trace、日志、成本账单、实时看板

**实现**：
- **Trace**：每个 WorkItem 的完整生命周期，含各阶段耗时、产物大小、重试次数
- **日志**：结构化日志（JSON），支持关键词搜索、等级过滤
- **成本**：Claude Code token 消耗、云资源消耗（如 git mirror 存储）
- **看板**：实时 dashboard：处理中的 WorkItem / 日成功率 / 平均耗时 / token 成本趋势

**技术选型**：待定（Python logging + 时序数据库，或集成第三方可观测平台）

**集成点**：EventPublisher 订阅所有领域事件，产出 ObservabilityEvent

**时间线**：与切片 2 并行启动，切片 3/4 时持续加深

---

### 并发与调度（Concurrency & Scheduling）

**目标**：支持多 worker 并行处理多个 WorkItem，避免冲突

**当前约束**：单线程处理，WorkItem 串行推进

**加深**：
- WorkItemRepository 支持"领取锁"（optimistic locking）：多个 worker 同时拉取可推进列表，但同一 WorkItem 仅一个 worker 可推进
- Workspace 隔离：每个 WorkItem 的 worktree/branch 名称唯一（基于 WorkItemId）
- 事件幂等：即使事件传递多次，结果相同

**技术选型**：SQLite WAL（写入预先日志）+ 乐观锁 version 字段

**时间线**：切片 3 后期启动

---

### 安全（Security）

**目标**：防止 prompt 注入、权限越界、凭证泄露

**关键威胁**：
- **Prompt 注入**：恶意 Requirement 包含指令，试图指挥 Claude Code 删除代码/提交恶意代码
- **权限越界**：GitLab token 权限过大，或 Feishu token 能访问非预期群聊
- **凭证泄露**：git/GitLab/Feishu token 被记录在日志或 trace 中

**防护措施**：
- **输入清理**：Requirement + ContextArtifact 在 ACL 边界做 HTML/markdown escape + 指令检测
- **Prompt 设计**：Claude Code 的 system prompt 明确指出"绝不可执行这些操作"（删除、提权等）
- **权限最小化**：git token 只读，GitLab token 仅限目标仓库，Feishu token 仅限特定群聊
- **凭证管理**：所有 token 从环境变量或密钥管理系统读取，永不记录日志
- **审计日志**：完整记录所有 Claude Code 的执行输入与输出，与需求和决策链链接

**SECURITY.md 规划**：见项目基线 B4 任务

**时间线**：与切片 2 并行启动，切片 3 前完成核心防护

---

## 时间线与里程碑

```
2026-07-16 ╔═══════════════════════════════════════╗
           ║  🎯 项目基线（0.1.1）- ✓ 已完成       ║
           ║  完成于：2026-07-16                    ║
           ║  - README + ROADMAP                    ║
           ║  - 架构图（5 张）                      ║
           ║  - ADR（3 个决策记录）                 ║
           ║  - 治理文件 + 质量门禁                 ║
           ╚═══════════════════════════════════════╝
                      ↓
2026-07-25 ╔═══════════════════════════════════════╗
           ║  🖥️ 控制台 + Project（0.1.2）- ✓ 交付 ║
           ║  - Project 领域聚合 + 端口             ║
           ║  - FastAPI 后端 + React 前端控制台     ║
           ║  - 本地仓库直挂 worktree               ║
           ╚═══════════════════════════════════════╝
                      ↓
           ╔═══════════════════════════════════════╗
           ║  🚀 切片 2：真实 ACL - ◐ 进行中       ║
           ║  目标：2-3 周                          ║
           ║  - Workspace/Context ✓ 已落地         ║
           ║  - Design/Review/Execution/Verify/    ║
           ║    Delivery 5 个 → 真实实现            ║
           ║  - E2E 冒烟测试 + Observability 基础   ║
           ╚═══════════════════════════════════════╝
                      ↓
           ╔═══════════════════════════════════════╗
           ║  🎨 切片 3：多类型重流程（待定）      ║
           ║  目标：3-4 周                          ║
           ║  - SmallChange / MediumFeature /       ║
           ║    ComplexFeature 完整支持             ║
           ║  - 强 Context 检索                     ║
           ║  - 执行沙箱隔离                       ║
           ╚═══════════════════════════════════════╝
                      ↓
           ╔═══════════════════════════════════════╗
           ║  🎯 切片 4：自动合并（待定）          ║
           ║  目标：2 周                            ║
           ║  - AutonomyDial 精细化                ║
           ║  - 信任梯度机制                       ║
           ║  → 无人值守！                         ║
           ╚═══════════════════════════════════════╝
```

---

## 关键成功要素

### 架构稳定性

✓ 已达成：六边形架构 + DDD 原则在切片 1 就已完整建立，后续切片只是在既定边界内填充实现

**持续关注**：
- 新特性必须符合职责铁律（核心域纯净、外部交互走 ACL）
- 限界上下文边界不可突破
- 产物只进不改的不变式保持强制

### 质量底线

✓ 已达成：切片 1 起以约 48 个测试建立核心覆盖，随控制台/适配器推进已扩至约 230 个后端测试（另有前端 vitest 套件），未来新切片应保持或提升测试覆盖率

**持续关注**：
- 每个切片完成时 `pytest -q` 全绿
- 重要功能的集成测试（端到端冒烟）
- 定期性能/稳定性压力测试

### 快速反馈

✓ 已达成：项目基线的 CI/CD 质量门禁（B5 任务，2026-07-16 完成）：本地 `ruff check` / `mypy src` + `.pre-commit-config.yaml` + `.github/workflows/ci.yml`（GitHub Actions）

**后续**：
- 切片 2 起：GitHub Actions CI 中加入真实 ACL 适配器的集成测试

### 人员与知识

**当前**：领域模型与实现已充分文档化（战略方向、垂直线设计、计划文档、内联注释）

**关键**：
- 新成员入职须通读《战略方向与领域模型》与《职责铁律》
- 代码评审时坚守边界与原则，不因短期压力而违反
- 定期同步会议复盘进展与设计决策

---

## 怎样参与

1. **选择一个切片或关切面**，与团队同步计划
2. **按既定架构与职责铁律编码**，参考《战略方向与领域模型》第 2/7 节
3. **提交前运行完整验收**：`pytest -q` + `mypy src` + `ruff check .`
4. **每个 commit 贴上追踪号**（如 `feat(slice2): implement WorkspacePort adapter`）
5. **完成后更新本 ROADMAP**，标记切片/任务完成时间与主要变更

---

## 常见问题

**Q：为什么用"垂直切片"而不是"分层开发"？**  
A：分层开发容易导致"底层都做完才能看到功能"的长反馈周期。垂直切片保证每个里程碑都能闭环运行，快速发现设计问题。

**Q：能加快进度吗？比如并行做多个切片？**  
A：不建议。每个切片都依赖前序的架构与实现。并行会导致集成冲突与重复工作。相反，专注于一个切片能加快总体交付。

**Q：为什么不一开始就实现所有端口？**  
A：过度工程。假适配器足以验证核心逻辑的正确性。等核心稳定后再逐个替换为真实实现，成本更低。

**Q：如何处理需求变更？**  
A：修订《战略方向与领域模型》（若影响架构边界），重新评估现有与未来切片的影响。简化需求（如减少支持的任务类型）可加快最近切片的交付。

---

**最后更新**：2026-07-25（与代码对齐；补入控制台里程碑、标注切片 2 进行中）  
**下一次计划评审**：（随迭代规划确定）
