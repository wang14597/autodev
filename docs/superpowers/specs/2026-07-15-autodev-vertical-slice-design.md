# AutoDev — 端到端薄垂直线设计

> 日期：2026-07-15
> 状态：设计已在头脑风暴中逐节获批，待用户通读评审
> 项目根目录：`autodev/`
> **架构基准**：本 spec 是《AutoDev — 战略方向与领域模型》（`docs/architecture/2026-07-15-strategic-direction-and-domain-model.md`）在"切片 1"范围内的实现级细化，须符合该基准；冲突以基准为准。

## 0. 架构对齐（DDD）

本 spec 遵循领域模型基准的**六边形架构（Ports & Adapters）**与职责铁律。术语映射：

| 本 spec 用语 | 领域模型（权威） |
|--------------|------------------|
| Task | **WorkItem**（唯一聚合根，一致性边界） |
| Engine | 应用层：跑 `TransitionRules` 推进聚合的循环 |
| Handlers（九阶段） | 应用服务：协调出站端口 + 领域服务，产出 Artifact |
| Adapters（Feishu/GitLab/ClaudeCodeRunner） | **ACL 适配器**，实现对应出站端口，翻译"外部↔领域" |
| Store | `WorkItemRepository` 端口 + SQLite 适配器 |
| Gate 控制器 | `GatePolicy` 领域服务 + `AutonomyDial` 值对象 |
| 工作区准备（3 模式） | `WorkspacePort` + Workspace 上下文 |

**须遵守的职责铁律**（详见基准第 2 节）：核心编排代码不得出现 git/GitLab/飞书/Claude 概念；外部交互一律走 ACL；外部异常在 ACL 边界翻译为领域 `StageOutcome{failureKind}`；产物只进不改；人审=挂起态。下文凡出现 "Task" 均指 **WorkItem**。

## 1. 背景与目标

构建一个 **AI 研发工作流编排平台**，让一个标准研发团队的工作——需求提出 → 收集上下文 → 设计方案 → 评审 → 按方案开发 → 设定验收标准 → 验收测试 → 提 MR 等待合并——借助 AI 实现自动化、规模化、效率化。

### 定位与约束（头脑风暴结论）

- **面向对象**：内部团队自用工具。取舍原则 = 优先落地、够用、快见效；不做多租户/通用产品化/生产级健壮性。
- **集成环境**：代码托管在 **GitLab**（MR）；需求、讨论、通知、文档在 **飞书 / Lark**。
- **自动化程度**：终极目标是**全自动无人值守**。但采用**旋钮式**落地策略——
  - 架构上支持全自动闭环（每阶段能自跑、自流转、可续跑）；
  - "是否需人确认"是**每类任务 · 每仓库可配置的开关**；
  - 初期在低风险任务类型 + 低风险仓库上打开无人值守，用真实结果积累信任后逐步放开。
  - 一句话：**架构按全自动设计，投产按信任梯度放开。**
- **任务范围**：从 Bug 修复/小改动，到中等特性，到复杂跨模块特性，全都要接 → 必须有**分诊（triage）**先分级、再决定流程深度与路由。
- **执行引擎**：真正改代码/跑测试的部分用 **Claude Code / Agent SDK**（headless 会话）。
- **编排器技术栈**：**Python**（团队已在用；Agent SDK / GitLab / 飞书均有成熟 Python 生态）。

## 2. 平台拆解与建设顺序

整个平台分为"骨干层"和"阶段层"两层：

```
骨干层 (一次建好，所有阶段复用)
  ① 编排引擎    状态机：任务在阶段间流转、失败重试、人类介入点
  ② 状态存储    任务、产物、历史、成本 (SQLite)
  ③ 集成适配器  GitLab 适配器 / 飞书适配器 / Claude Code Runner
  ④ 门禁与人审  每类任务·每仓库可配的"是否需人确认"旋钮 + 飞书审批
  ⑤ 可观测性    每任务 trace、日志、成本、看板

阶段层 (骨干依次推过的可插拔单元)
  [1 需求接入]→[2 分诊分级]→[3 上下文收集]→[4 方案设计]
    →[5 方案评审]→[6 编码执行]→[7 验收标准]→[8 验收测试]
    →[9 提 MR / 编排合并]
```

**核心建设判断**：不先把通用骨干抽象地建完，而是先打**一条最薄的端到端垂直线**——只支持最简单的任务类型，但九个阶段全部最小化跑通——先拿到能闭环的骨架，再逐个阶段加深。

**建设顺序**：

- **第一块砖（本设计的范围）**：一条 "小改动 / 明确 Bug" 任务的端到端薄垂直线。飞书丢需求 → 收集上下文 → 生成极简方案 → Claude Code 编码 → 跑测试验收 → 提 MR → 飞书通知。合并前留人审门禁（旋钮式，后续放开）。
- **后续切片（各自独立设计→计划→实现）**：加深分诊 → 加深复杂/中等特性的"设计+评审"重流程 → 更强的上下文检索 → 逐步放开自动合并。

## 3. 实现方案选择

在"编排引擎多重"这条轴上比较了三种方案：

- **A 极简线性管道**：顺序函数调用，最快见效，但无重试/续跑/门禁，撑不起无人值守目标。
- **B 自建轻量状态机 + 垂直线（选定）**：精简但真实的状态机（显式状态、转移、持久化、重试、人审=挂起态），阶段逻辑只实现小改动一类。够真能生长，又不过度设计。
- **C 成熟工作流引擎（Temporal/Prefect/LangGraph）**：工业级健壮但重依赖、学习成本高，抽象未必贴合"AI 阶段 + 人审挂起"，违背快见效。

**选定方案 B。** 将来某阶段确需复杂并发编排，再局部替换为 C。

## 4. 整体架构

系统是围绕 Claude Code headless 会话的 Python 编排器，核心是一个精简状态机。

```
                         ┌───────────────────────┐
   飞书需求源 ──trigger──►│      Task Store        │  SQLite
   (消息/文档/多维表格)    │  任务·状态·产物·历史·成本 │
                         └───────────┬───────────┘
                                     │ 读/写
                    ┌────────────────▼────────────────┐
                    │        编排引擎 (Engine)          │
                    │  取任务→看当前状态→跑对应handler   │
                    │  →拿到转移结果→持久化→继续/挂起/停 │
                    └────────────────┬────────────────┘
       ┌──────────────┬──────────────┼──────────────┬───────────────┐
       ▼              ▼              ▼              ▼               ▼
  阶段处理器们      Gate/人审控制   Feishu 适配器   GitLab 适配器   ClaudeCode Runner
  intake/triage/   (旋钮:某类任务  发通知·发卡片   工作区准备·     拉起 headless
  context/design/   ·某仓库是否    ·请求审批·      push·开 MR      会话干活·收产物
  .../submit_mr     需人确认)      接收回调
```

三个架构要点：

1. **状态即进度，引擎无状态**：任务的 `state` 字段就是它走到哪了。引擎本身不持有状态，重启后从 Store 里任务的 `state` 接着跑 —— 这就是断点续跑。
2. **人审是一等状态**：需人拍板时 handler 把任务转到 `WAIT_HUMAN` 并记下"在等什么"，引擎挂起。飞书审批回调到达时转回对应状态继续。无人值守 = 关掉该门禁开关，handler 直接往下走。
3. **worker 循环驱动**：一个 worker 进程不断从 Store 捞"可推进"的任务往前推一步。单进程串行起步，并发是后续的事。

## 5. 组件与职责边界

每个单元回答三件事：干什么 / 怎么用 / 依赖谁。统一的 handler 契约：`handle(task, ctx) -> Transition`。

| 组件 | 干什么 | 怎么用 / 契约 | 依赖 |
|------|--------|--------------|------|
| **Task** | 描述任务全部状态：`id/type/repo/state/gate_config/payload/artifacts/history/cost/timestamps` | 纯数据模型 | 无 |
| **Store** | Task 增删查改；捞可推进任务 | `save(task)/get(id)/claim_runnable()` | SQLite |
| **Engine** | 按 `state` 找 handler，跑它，拿 `Transition`，持久化，决定继续/挂起/停 | `advance(task)`；worker 循环调用 | Store、handler 注册表 |
| **Handlers×9** | 各阶段具体逻辑；彼此不互调，只经 `artifacts` 传产物 | `handle(task, ctx) -> Transition(next_state, artifacts, retry?, suspend?)` | 适配器、Gate |
| **FeishuAdapter** | 读需求、发通知/卡片、请求审批、接收回调 | 接口，测试用假实现 | 飞书 API |
| **GitLabAdapter** | 工作区准备（见 §6）、push、开 MR、查流水线 | 接口，测试用假实现 | GitLab API + 本地 git |
| **ClaudeCodeRunner** | 在工作区拉起 headless Claude Code，喂 prompt+上下文，捕获产物 | 接口，测试用假实现 | Claude Code / Agent SDK |
| **Gate 控制器** | 查"此类任务+此仓库+此阶段是否需人确认" | `needs_human(task, stage) -> bool` | 配置 (YAML/DB) |
| **入口: trigger** | 从飞书源创建 task 落库 | CLI / 事件 | Store、FeishuAdapter |
| **入口: worker** | 循环推进可运行任务 | 常驻进程 | Engine、Store |
| **入口: resume** | 飞书审批回调 → 唤醒 `WAIT_HUMAN` 任务 | 回调处理 | Store、FeishuAdapter |

## 6. 工作区准备（Workspace Provisioning）

获取工作区分场景。本地维护一个 **repo mirror 缓存目录**（各仓库规范 clone）；每个 task 的工作区从 mirror 上 `git worktree add` 出独立目录 + 独立分支，任务间互不干扰。

| 模式 | 触发场景 | 做法 |
|------|---------|------|
| `worktree`（默认） | 已有仓库上的改动/修复/特性 | 本地有 mirror，直接 `git worktree add` 拉带新分支的独立工作目录 |
| `clone` | 已有仓库但本地未缓存 | 先 clone/更新到 mirror，再按 `worktree` 拉 worktree |
| `create` | 全新项目 (greenfield) | GitLabAdapter 新建仓库 + 初始化，再拉 worktree |

- **模式在 TRIAGE 决定**：分诊判断目标仓库存不存在、是否全新项目，把 `workspace_mode` 写进 `artifacts.triage`；CONTEXT 据此准备工作区，把 `worktree_path/branch` 写进 `artifacts.context`。
- 清理用 `git worktree remove` 删 worktree 和分支残留，**mirror 保留**复用。

## 7. 状态与数据流

### 状态集合

`INTAKE → TRIAGE → CONTEXT → DESIGN → REVIEW → IMPL → ACCEPT → VERIFY → SUBMIT_MR → DONE`，外加 `WAIT_HUMAN`（挂起）、`FAILED`（终态）。

### 数据流（走一个真实任务）

触发例：飞书里"XX 仓库登录接口报错信息拼错了，`passwrod` 应为 `password`"。`trigger` 落成 task：`type=small_change, repo=xxx, state=INTAKE, payload=原文`。

```
INTAKE     解析需求原文 → artifacts.intake = {目标, 涉及仓库, 验收线索}
TRIAGE     判级 small_change + 定 workspace_mode → artifacts.triage = {level, confidence, workspace_mode}
CONTEXT    按 workspace_mode 准备工作区(worktree/clone/create)，再检索
           → artifacts.context = {worktree_path, branch, 相关文件, 摘要}
DESIGN     小改动走极简方案：一句话改动说明 + 影响文件清单 → artifacts.design
REVIEW     AI 自审方案；Gate 查是否需人审 → 需要则 WAIT_HUMAN → artifacts.review = {通过, 意见}
IMPL       ClaudeCodeRunner 在工作区按方案改代码 + 自跑测试 → artifacts.impl = {diff, 测试结果, 摘要}
ACCEPT     生成验收标准 (报错文案正确 + 相关测试通过 + 无回归) → artifacts.accept = {验收清单}
VERIFY     按验收清单跑测试/lint/构建；不过则回 IMPL 重试(上限3) → artifacts.verify = {通过, 各项结果}
SUBMIT_MR  建分支·push·开 MR，MR 描述引用需求+方案+验收结果 → artifacts.mr = {mr_url, 分支}
DONE       飞书通知"任务完成，MR 待合并 <链接>"(合并前留人审门禁)
```

关键流转规则：

- **产物只进不改**：每阶段只往 `artifacts` 追加自己那块，后续阶段读前面产物。任何一步失败，前面成果都还在，续跑不用重来。
- **VERIFY 失败回 IMPL**：带重试计数（上限 3），把失败原因带回让 Claude Code 针对性修；超上限转 `FAILED` 退人。
- **工作区隔离**：每 task 独立 worktree + 分支；DONE 后清理，FAILED 保留供排查。
- **无人值守旋钮两处**：REVIEW 后人审、SUBMIT_MR 后合并。初期都开着（挂起等人），信任够了按仓库/任务类型逐个关掉。

## 8. 错误处理与兜底

**① 失败分类**
- 瞬时错误（网络、API 限流/超时、会话卡死）→ 可重试。
- 阶段逻辑失败（改不动、VERIFY 没过、方案被否）→ 有限重试或回退上一阶段。
- 致命错误（配置错、仓库不存在、权限不足）→ 不重试，直接 `FAILED` 退人。

**② 重试策略**
- 每 handler 带 `max_retries` + 指数退避，只对瞬时错误重试。
- VERIFY→IMPL 单独计数（默认上限 3）。重试/回退记进 `history`，超上限转 `FAILED`。

**③ 幂等与续跑**
- 引擎无状态 + 崩溃后从当前 `state` 重跑该阶段 → handler 必须能安全重复执行。
- 有副作用的阶段加幂等护栏：`SUBMIT_MR` 先查分支是否已有 MR，有则复用不重开；工作区准备先查 worktree 是否已存在。

**④ 超时**
- 每阶段、尤其每个 Claude Code 会话带墙钟超时。卡死会话被杀 → 当作可重试瞬时失败。

**⑤ 成本**
- 每 task 累计 token 成本，**仅记录用于可观测性/看板，不设上限、不做拦截**（当前决定）。

**⑥ 退人时给足上下文**
- 转 `FAILED`/`WAIT_HUMAN` 时，飞书通知带：卡在哪个阶段、错误摘要、已有产物、worktree 路径（人可进去看现场）。
- 失败任务 worktree 不自动删，保留排查；仅 `DONE` 清理。

**⑦ 防死循环**
- 所有重试/回退有硬上限，无任何无限打转路径。最坏结果永远是"干净地 `FAILED` 并通知人"。

## 9. 测试策略

**① 单元测试（主力，快）**
- Engine：假 handler 验证状态转移、重试计数、回退、`WAIT_HUMAN` 挂起/唤醒、超上限转 `FAILED`。覆盖要厚。
- 每个 handler：注入假适配器（fake Feishu/GitLab/ClaudeCodeRunner），喂构造 task，断言 `Transition` 与写入 `artifacts` 的内容。
- Gate 控制器：各配置下 `needs_human` 判定。
- 因适配器是接口、产物只进不改，这些测试不碰真实外部系统，秒级完成。

**② 适配器契约测试**
- 每适配器一份契约测试：假实现与真实现跑同一组断言，保证假的不跑偏。
- GitLabAdapter 真实现用本地临时 git 仓库验证 worktree/分支/MR 逻辑；飞书用录制响应或 sandbox。

**③ 端到端冒烟（一条，慢，手动/CI 触发）**
- 真实小仓库 + 真造"拼写修复"任务，全链路跑到开出 MR。**这条垂直线的验收标准 = 它能自动修好一个 typo 并提 MR。**

## 10. 技术栈

- 编排器：Python
- 状态存储：SQLite
- 执行引擎：Claude Code / Agent SDK（headless）
- 代码托管：GitLab（API + 本地 git worktree/mirror）
- 协作/通知/审批：飞书 / Lark

## 11. 非目标（本切片明确不做）

- 中等/复杂特性的重流程设计与评审（后续切片）。
- 自动合并（初期一律人审门禁，合并留给人）。
- 多租户、通用产品化、Web 控制台（后续可选）。
- 高级上下文检索（向量库/知识图谱等）——初期靠 Claude Code 在 worktree 内检索即可。
- 并发调度（起步单进程串行）。
- 成本上限/预算拦截（仅记录）。
