# 文档一致性 CI — 设计文档

> 日期：2026-07-16
> 状态：设计（方向已认可，待评审后进入实现计划）
> 关联：审计教训见本会话 docs-sync 修复；质量门禁现状见 `.gitlab-ci.yml`（将迁移）。

## 1. 背景与目标

AutoDev 是个文档密集的大项目，文档极易滞后于代码。真实教训（本项目审计中反复出现）：漂移**不是"忘了改文档"，而是"文档写了但事实错了"**——

- 伪造的代码符号：IntakeHandler（实为函数 `handle_intake`；本例中 IntakeHandler 本身不是真实符号）、CollaborationPort（不存在）、WorkItemTriaged（不存在的事件）。
- 数字不一致：状态数 11 vs 实际 12；产物数 8 vs 写成 9；端口 8 vs 9。
- 过期前向引用：`(规划中)`、`coming in B5`——里程碑落地后未清理。
- CHANGELOG 陈旧：已完成项仍挂在"Planned"。

**目标**：在合并 PR 前，用 CI 阻止"功能改动未同步/写错文档"的 PR 进入主干。**核心原则：能自动断言正确性的地方硬阻塞；只能靠判断的地方给建议，不阻塞。**

## 2. 平台对齐（关键前提）

必须区分两个"平台"，此前混淆了：

| 关注点 | 平台 | 说明 |
|--------|------|------|
| **平台运行时集成**（AutoDev 开发的目标项目） | **GitLab** | DeliveryPort/Workspace ACL 对接 GitLab（拉取/创建仓库、开 MR）——不变 |
| **AutoDev 本仓库托管与 CI** | **GitHub** | 本项目源码在 GitHub → 本仓库 CI = **GitHub Actions**；协作单位 = **PR**（非 MR） |

**因此本次需要的平台迁移（纳入实现范围）：**
- 新增 `.github/workflows/` 承载本仓库 CI（质量门禁 + 文档一致性）。
- 把 B5 的 `.gitlab-ci.yml`（lint/type/test）迁移为 GitHub Actions job，然后**删除 `.gitlab-ci.yml`**（本仓库不在 GitLab 跑）。
- 把 `.gitlab/merge_request_templates/default.md` 迁移为 `.github/pull_request_template.md`（内容等价，措辞 MR→PR）。
- `CODEOWNERS` 移到 `.github/CODEOWNERS`（GitHub 原生位置；根目录亦可，统一到 `.github/`）。
- 全仓文档中"给**本仓库**贡献"语境的 "GitLab MR" 措辞改为 "GitHub PR"；描述**产品对接目标项目**的 "GitLab MR" 保持不变（这是产品行为）。

> 注意：这是"本仓库协作在 GitHub、产品对接在 GitLab"的双轨事实，文档需明确二者，避免再次混淆。

## 3. 三层设计

### 第 1 层：确定性检查（阻塞）— 复用现有测试门禁

实现为 `tests/docs/test_doc_consistency.py`，随 `pytest` 在 CI 跑（无需新门禁基础设施）。四项断言，全部确定性、低误报：

**1.1 符号存在性（杀"伪造符号"）**
- 从代码构建"已知符号集"：`src/autodev/**` 中所有 `class X`、`def x`、Enum 成员名。
- 从受检文档中提取反引号标识符 `` `Foo` ``，**筛出看起来是代码符号的**（启发式：以 `Port`/`Artifact`/`Policy`/`Event`/`Handler`/`Repository` 结尾的 CamelCase，或 `handle_*`/`snake_case` 且含下划线）。
- 断言：每个这样的 token 必须在已知符号集中；否则失败并列出漂移符号。
- 允许清单：`docs/.doc-allowlist.txt` 收纳合法但非代码的例外（如领域概念 CollaborationPort 若仅出现在"未来端口"语境需显式登记，或改写为非反引号）。

**1.2 计数一致（杀"数字漂移"）**
- 代码真值由测试直接计算：`len(WorkflowState)`、artifact 类数、`*Port` 数、事件类数、`pytest` 用例数（或从已知常量）。
- 文档中的计数以带标记的行承载，例如 `<!-- fact:workflow_states -->12`，测试解析标记行并与真值比对。
- 落地策略：**优先单一真源**（见 §4），仅对确需在文档正文出现的计数用 `fact:` 标记。

**1.3 内链解析（杀"坏链/过期前向引用"）**
- 扫所有受版本管理的 `*.md`，提取相对路径内链，断言目标文件存在。
- 断言：文档中不得残留 `(规划中)`/`coming in B<N>` 等"过期前向引用"模式指向**已存在**的目标（前向引用只允许指向确实还不存在的东西）。

**1.4 Mermaid 渲染（杀"坏图"）**
- CI 中 `npx -y @mermaid-js/mermaid-cli` 逐块渲染 `docs/**/*.md` 的 mermaid，失败即挂。
- 本地无 CLI 时测试跳过并告警（`pytest.mark.skipif`），CI 里必跑。

### 第 2 层：路径→文档映射（阻塞 + 逃生舱）

**配置** `docs/doc-ownership.yml`：声明"某代码路径变更 ⇒ 候选相关文档"。示例：
```yaml
rules:
  - paths: ["src/autodev/domain/ports.py"]
    docs:  ["README.md", "docs/architecture/diagrams.md", "CHANGELOG.md"]
  - paths: ["src/autodev/domain/enums.py"]
    docs:  ["docs/architecture/diagrams.md", "CHANGELOG.md"]
  - paths: ["src/autodev/**"]            # 任何功能改动
    docs:  ["CHANGELOG.md"]
```
**脚本** `scripts/check_doc_impact.py`（在 GitHub Actions PR 事件跑）：对 PR 的变更文件集，命中规则却未改动对应文档 → 失败，明确列出"改了 X 但没更新 Y"。

**逃生舱（避免误报、留痕）**：满足任一即跳过对应规则——
- PR 打标签 `docs:none-needed`；或
- 任一提交尾注 `Docs-Impact: none — <理由>`。
CI 把跳过决定回显到 PR 日志/评论，使"无需文档"成为**显式、可审计**的决定。

**CHANGELOG-or-skip**：`src/autodev/**` 任意改动必须伴随 `CHANGELOG.md` 变更或显式 skip——业界成熟做法，性价比最高，单列为一条规则。

### 第 3 层：AI 顾问（不阻塞，本地 `pre-push` 钩子）

**平台约束**：本仓库使用的 Anthropic key 仅在内网可用，GitHub 云端 runner 无法访问该 key，因此第 3 层**不能**做成 GitHub Actions job（原设计如此，已废弃，见下方"变更记录"）。

改为**本地 `pre-push` 钩子**：`scripts/docs_advise.py`，经由 `.pre-commit-config.yaml` 的 `local` repo、`stages: [pre-push]` 接入。开发者执行 `git push` 时，在**本机**（已连 VPN、本地已登录 Claude Code）跑 headless `claude -p`：输入本次改动相对上游分支的 `src/**` diff，让其判断"本次改动是否使某文档过时"，以终端输出的形式给出疑似清单。

- **绝不硬阻塞**：`scripts/docs_advise.py` 的 `main()` 恒返回 0；LLM 非确定性、diff 为空、runner 异常（未登录/无网络/超时）均优雅降级为提示信息，不阻止 push。
- **环境不可用则跳过**：不在内网/未连 VPN/本地无 Claude Code 时，顾问静默跳过或打印"顾问运行失败(不阻塞)"，push 照常进行。
- 一次性安装：`pre-commit install --hook-type pre-push`；也可手动运行 `python scripts/docs_advise.py`。
- 不再依赖 `ANTHROPIC_API_KEY` repo secret（原云端方案的前提），也不产生 PR 评论——仅本机终端输出，供开发者 push 前参考。

**变更记录**：原设计（见下）为 GitHub Actions job（`pull_request` 触发）跑 headless `claude -p`、以 **PR 评论**输出疑似清单，需要 `ANTHROPIC_API_KEY` 作为 repo secret。该方案因内网 key 限制无法在云端 runner 使用，已改为上述本地钩子方案；`.github/workflows/docs-advisor.yml` 已移除。

## 4. 根治手段：单一真源，减少可漂移的重复

检查漂移是治标；**消除重复事实是治本**。原则：**能从代码派生的清单/计数，不手写第二份。**
- 易变清单（端口名、状态名、产物名）在文档里只写"完整列表见 `ports.py`/`enums.py`"，不复制。
- 确需正文出现的计数，用 §1.2 的 `fact:` 标记 + 测试对拍，或由脚本从代码**生成**该段。
- ADR/设计文档记录"为什么"（相对稳定），README/CHANGELOG 记录"是什么/变了什么"（易变，重点受检）。

## 5. CI 编排（GitHub Actions）

- `.github/workflows/ci.yml`：`push` + `pull_request`。Jobs：
  - `lint`（`ruff check .`）、`type`（`mypy src`）、`test`（`pytest -q`，含 `tests/docs/`）、`mermaid`（渲染校验）、`doc-impact`（`scripts/check_doc_impact.py`，仅 `pull_request`）。
- 第 3 层不在 GitHub Actions 编排之列：改为本地 `pre-push` 钩子（`scripts/docs_advise.py`，见第 3 节），随开发者 `git push` 在本机运行，不出现在云端 workflow 或分支保护检查列表中。
- **分支保护**：`main` 要求 `lint/type/test/mermaid/doc-impact` 五个检查通过方可合并（第 3 层为本地钩子，不接入分支保护）。
- 删除 `.gitlab-ci.yml`；`.github/pull_request_template.md` 承载 PR 模板（含"文档已同步？/Docs-Impact 尾注"提示）。

## 6. 渐进上线

1. **阶段一**：平台迁移（GitHub Actions 承接 lint/type/test）+ 第 1 层四项确定性检查。零误报、纯收益，先合并。
2. **阶段二**：第 2 层映射 + 逃生舱 + CHANGELOG-or-skip。
3. **阶段三**：第 3 层 AI 顾问（本地 `pre-push` 钩子，一次性 `pre-commit install --hook-type pre-push`）。

## 7. 非目标
- 不追求"语义级"文档正确性自动化（那是第 3 层顾问 + 人审的事）。
- 不阻塞在任何 LLM 判断上。
- 不改动产品与 GitLab 的运行时集成（DeliveryPort 等仍是 GitLab）。
- 不做文档自动生成框架（Sphinx/mkdocs 等）——本期只做"一致性检查 + 少量单一真源"，重框架留后续按需。

## 8. 验收标准
- 本仓库 CI 在 GitHub Actions 上跑通 lint/type/test/mermaid/doc-impact；`.gitlab-ci.yml` 已移除。
- 故意制造一次漂移（改 `enums.py` 加一个状态但不更新文档计数、或在文档写一个不存在的 `FooPort`）→ 第 1/2 层 CI 失败。
- 合法的纯重构 PR 配 `Docs-Impact: none` → CI 通过。
- 现有 48 测试 + 新增文档一致性测试全绿；`docs/doc-ownership.yml` 覆盖核心路径。
