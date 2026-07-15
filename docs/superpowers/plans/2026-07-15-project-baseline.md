# AutoDev 项目基线 Implementation Plan

> **For agentic workers:** 用 subagent-driven-development 逐任务执行；每任务后做 spec+quality 评审，最后整支评审。这些是一次性工程资产，不走 TDD，但每个任务必须有**可验证的验收动作**（渲染检查 / 实跑 lint·type·test / 链接解析）。

**Goal:** 给 AutoDev 补齐"专业项目必备资产"：门面文档、可渲染架构图、决策记录、协作治理文件、质量门禁配置——与功能解耦、一次性、低风险。

**Architecture:** 纯新增文件 + 少量 `pyproject.toml` 工具配置；不改任何 `src/` 运行时逻辑（质量门禁任务若 lint/type 报问题，只做最小、无行为变更的修正）。

**Tech Stack:** Markdown、Mermaid（GitLab 原生渲染）、ruff、mypy、pre-commit、GitLab CI。

## Global Constraints
- 不改 `src/autodev/**` 的运行时行为；质量门禁任务允许的修改仅限：格式化、import 整理、类型标注、无行为变更的微调。
- 所有文档用简体中文为主、术语与 `docs/architecture/2026-07-15-strategic-direction-and-domain-model.md` 的统一语言一致（WorkItem、限界上下文、铁律、ACL 等）。
- Mermaid 图必须语法正确、能在 GitLab/GitHub 渲染。
- 质量门禁任务结束时，`ruff check`、`mypy src`、`pytest -q` 三者必须本地实跑通过（48 tests 保持绿）。
- 提交遵循 Conventional Commits；提交人 `AutoDev <autodev@local>`，body 末尾附 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。

---

### Task 1: README + ROADMAP（项目门面）

**Files:** Create `README.md`, `ROADMAP.md`

**内容要求：**
- `README.md`：一句话定位 → 背景与目标（内部自用、GitLab+飞书、无人值守旋钮、Claude Code 执行、Python）→ 架构一览（六边形/Ports&Adapters + 状态机引擎，引用 `docs/architecture/…` 与 `docs/superpowers/specs/…`）→ 仓库结构（domain/application/adapters/tests 各职责一行）→ 快速开始（`python3 -m venv venv && . venv/bin/activate && pip install -e '.[dev]' && pytest -q`）→ 当前状态（切片 1 行走骨架完成、48 测试、9 端口中 2 真实 7 假、真实 ACL 属计划 2）→ 文档索引（架构基准/spec/plan/ADR/roadmap 链接）。
- `ROADMAP.md`：项目基线（本批次）+ 切片 1（已完成）+ 切片 2（真实 ACL + E2E 冒烟）+ 切片 3（中/复杂特性重流程、强上下文）+ 切片 4（信任梯度放开自动合并）+ 横向（可观测/并发/安全）。标注状态与依赖。

**验收：** 所有 markdown 内链指向真实存在的文件（逐个 `test -e` 验证）；无 TODO 占位；快速开始命令与仓库实际一致。

---

### Task 2: 架构图（Mermaid，可渲染）

**Files:** Create `docs/architecture/diagrams.md`

**内容要求（5 张 Mermaid 图，每张配一句说明）：**
1. **系统架构 / 六边形**：核心编排域在中心，出站端口 → ACL 适配器（Workspace/Context/Design/Review/Execution/Verification/Delivery/Repository/EventPublisher），标注哪 2 个已实现、哪 7 个待实现。用 `flowchart`。
2. **限界上下文映射**：核心(编排) / 支撑(Intake,Solution) / 通用(Workspace,Execution,Verification,Delivery,Collaboration,Observability)，标注 Customer-Supplier / 发布语言 / 事件订阅关系。用 `flowchart`。
3. **WorkItem 状态机**：`stateDiagram-v2`，INTAKE→…→DONE，含 WAIT_HUMAN 挂起/唤醒、VERIFY→IMPL 与 REVIEW→DESIGN 回退、任意态→FAILED。
4. **阶段时序 / 数据流**：`sequenceDiagram`，一个 small-change 任务从 create 经 worker 推进九阶段到 MR 待合并 + 人审 resume。参与者：Trigger、Engine、Handlers、Ports、Store、EventBus。
5. **WorkItem 聚合数据模型**：`classDiagram`，WorkItem + 值对象/产物族（版本化 artifact_versions）+ 关系。

**验收：** 每个 mermaid fenced block 语法正确（用 mermaid 校验器或 `npx @mermaid-js/mermaid-cli` 若可用；否则逐块人工核对括号/箭头/关键字）；状态机图的转移与 `src/autodev/domain/work_item.py` 的 ALLOWED 表一致；上下文/端口与 `ports.py` 一致。

---

### Task 3: ADR（架构决策记录）

**Files:** Create `docs/adr/0000-template.md`, `docs/adr/0001-lightweight-state-machine.md`, `docs/adr/0002-versioned-artifacts.md`, `docs/adr/0003-domain-vocabulary-neutralization.md`, `docs/adr/README.md`（索引）

**内容要求：** 标准 ADR 格式（Title / Status / Context / Decision / Consequences / Alternatives considered）。
- 0001：选自建轻量状态机（方案 B），拒绝极简线性(A)与成熟引擎(C)——理由=无人值守目标需重试/续跑/门禁挂起 + 快见效。
- 0002：产物版本化（append-only 版本列表）解决"只进不改"与回退重跑冲突；拒绝覆盖式与多 key。
- 0003：铁律#1 中性化——领域去 git/GitLab 词汇（WorkspaceMode REUSE/FETCH/CREATE、location/label、change_request_url），git 机制归 ACL。
- Status 均为 Accepted，注明日期 2026-07-15。

**验收：** 五个文件齐全、格式一致、无占位；索引 README 列出全部 ADR；决策内容与已合并代码/文档一致。

---

### Task 4: 协作与治理文件

**Files:** Create `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`, `CHANGELOG.md`, `.gitlab/merge_request_templates/default.md`, `CODEOWNERS`

**内容要求：**
- `CONTRIBUTING.md`：环境搭建、跑测试/lint/type、目录约定、Conventional Commits、分支策略、"核心域不得引入外部 SDK（铁律#1）""产物版本化不可覆盖"等本项目硬约束。
- `SECURITY.md`：漏洞上报方式（占位联系人）；**AI 自主改代码的威胁模型要点**：执行沙箱边界、不可信输入(需求/仓库内容)的 prompt 注入、凭证最小权限、自动合并护栏——列为"计划 2/后续必须落实"。
- `LICENSE`：内部专有声明（`Proprietary — internal use only, All rights reserved`）；文件头注明可按需替换。
- `CHANGELOG.md`：Keep a Changelog 格式，`0.1.0 - 2026-07-15` = 切片 1 行走骨架（领域/引擎/适配器/48 测试）。
- MR 模板：变更说明 / 关联 spec·plan·ADR / 铁律自查清单 / 测试证据 / 评审门禁。
- `CODEOWNERS`：占位（`* @your-team`），注明按团队填。

**验收：** 六个文件齐全、无占位残留（占位处显式标注"待填"）；CHANGELOG 版本与内容属实。

---

### Task 5: 质量门禁（CI + lint + type + pre-commit + 依赖）

**Files:** Modify `pyproject.toml`；Create `.pre-commit-config.yaml`, `.gitlab-ci.yml`

**内容要求：**
- `pyproject.toml`：`[project.optional-dependencies] dev` 增加固定下限版本的 `ruff`、`mypy`；加 `[tool.ruff]`（line-length、select 基础规则集）、`[tool.mypy]`（`python_version=3.11`，对 `src/autodev` 开 `disallow_untyped_defs` 视情况；务实为先，保证能过）。
- `.pre-commit-config.yaml`：ruff（lint+format）、mypy、pytest（或 trailing-whitespace/eof 等基础钩子）。
- `.gitlab-ci.yml`：三 stage —— `lint`(`ruff check .`)、`type`(`mypy src`)、`test`(`pytest -q`)；用 python:3.11 镜像，装 `.[dev]`。

**验收（必须实跑）：** 本地 `. venv/bin/activate` 后依次跑 `ruff check .`、`mypy src`、`pytest -q` 全部通过（48 tests 绿）。若 ruff/mypy 报问题，只做**无行为变更**的最小修正（格式、import、类型标注）或在配置里务实收敛规则；不得改运行时逻辑。把三条命令的输出写进报告。

---

## Self-Review
- 覆盖：README/ROADMAP、5 图、3 ADR+模板+索引、6 治理文件、CI+lint+type+pre-commit+依赖——对应我给用户的基线清单全部条目。
- 占位扫描：文档里除显式"待填/占位"（联系人、CODEOWNERS、LICENSE 可替换）外无遗漏 TODO。
- 一致性：状态机图/上下文图/README 状态描述与已合并代码一致（48 测试、2/9 真实端口、方案 B、版本化、中性化）。
