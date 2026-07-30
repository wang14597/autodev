# DesignPort 真实适配器（方案设计阶段落地）设计

> 日期：2026-07-29
> 状态：**待定稿**（brainstorming 决策已定，待用户确认后转实现计划）
> 背景：切片 2 已落地 Workspace（F1）/ Context（F3）/ Triage（LLM）三个真实适配器，DESIGN 及之后仍为 `UnavailableStage` 桩。本设计把**第 4 个**真实适配器 `DesignPort` 落地，让流水线在既有自主/门禁框架下真实推进到「方案设计」阶段并在控制台展示。
> 架构基准：docs/architecture/2026-07-15-strategic-direction-and-domain-model.md
> 前序：docs/superpowers/specs/2026-07-20-f3-context-acl-design.md（本设计与其同构）、docs/superpowers/specs/2026-07-27-llm-triage-autonomy-switch-design.md（自主/门禁框架）

## 0. 已确认决策（brainstorming）

1. **产物是一份 Markdown 文档**，与 Context 上下文简报完全对等：持久化到 `~/.autodev/workitems/<id>/design-<rand>.md`，`DesignArtifact` 简化为**纯指针**（对齐 `ContextArtifact`）。
2. **复用 `ClaudeCodeRunner` 基座**，在 worktree 内只读跑 `claude`（permission-mode `plan`）——能读到真实代码，产出"落地过"的方案。**否掉**直连 Messages API（无仓库工作目录、拿不到真实代码，只适合 triage 那种小枚举分类）。
3. **不注入 context 文档内容**，只把 `context.context_file` 的**绝对路径**写进 prompt，由 Claude Code CLI 自行读取。
4. **不做结构化字段抽取**，产物只有一个 md 文件指针。
5. **单遍生成，不做自审复核**（与 Context 的两遍不同——本阶段用户明确要求单遍）。
6. **完整垂直线**：真实适配器 + 接入有界驱动（RUN 扩到 DESIGN）+ 前端渲染方案面板。

## 1. 非目标

- 真实 Review / Execution / Verification / Delivery（仍属后续迭代，保持 `UnavailableStage` 桩）。
- REVIEW_GATE 的真实评审逻辑（本迭代驱动停在 REVIEW 状态，不触达 review 桩）。
- 方案的结构化解析、多轮设计评审、跨仓库上下文（切片 3）。
- 飞书/Lark 集成、prompt 注入防护（延续排除）。

## 2. 流程与状态机（在既有框架内，仅"打通" DESIGN）

```
INTAKE → TRIAGE(LLM) → CONTEXT(收集简报)
   → 【上下文后决策 · AutonomyPolicy，既有逻辑不变】
        分诊不可用 / 置信过低 / 自主关 → 挂起 CONTEXT_GATE(WAIT_HUMAN)
        开 & 意图 = CONSULTATION        → finish → DONE(仅收集)
        开 & 意图 = ACTIONABLE          → DESIGN ← 【本次打通】
   CONTEXT_GATE 人工 proceed             → DESIGN ← 【本次打通】
   DESIGN(真实: 产出方案 md 文档) → REVIEW(桩, RUN 外) → 驱动停住
```

`handle_design`（handlers.py:82）已存在且正确（`ctx.designer.propose(requirement, context)`），无需改动领域/应用层——本迭代只替换端口实现、扩驱动边界、加前端投影。

## 3. 适配器 `ClaudeDesignAdapter`（`adapters/design_claude.py`）

结构镜像 `ClaudeContextAdapter`，但**单遍**、全程只读。

```python
class ClaudeDesignAdapter:
    def __init__(self, runner, autodev_home, id_gen=...): ...

    def propose(self, requirement, context) -> DesignArtifact:
        doc  = self._generate(requirement, context)   # 单遍
        path = self._persist(context, requirement, doc)
        return DesignArtifact(design_file=str(path))
```

- **`_generate`**：在 `context.workspace_location`（worktree）里跑 `claude`。prompt 内容：
  - 需求 `requirement.goal`；
  - context 文档的**绝对路径** `context.context_file`，明示"可先读该文件了解已收集的上下文"；
  - 要求只读调查代码后产出固定小节的 Markdown 方案：`## 方案概述` / `## 改动清单`（逐文件 + 理由）/ `## 实现步骤` / `## 风险与取舍`；
  - 强调只读、不修改任何文件、只输出 Markdown 文档本身（无额外解释）。
  - `self._runner(prompt, Path(context.workspace_location)).strip()`。
- **`_persist`**：工作项 id 取自 `Path(context.workspace_location).name`（与 Context 一致）；写 `~/.autodev/workitems/<id>/design-<id_gen()>.md`，带头部（需求 / 分支）。`mkdir(parents=True, exist_ok=True)`。
- **失败翻译**（铁律 3/7）：`claude` 异常由 `ClaudeCodeRunner` 已翻译成 `StageError`（TRANSIENT/FATAL/LOGIC），适配器**不吞、直接上抛**，交引擎按 `RetryPolicy` 重试/收敛 FAILED。context 文件读不到发生在 claude 侧（模型仅少了上下文，方案照出，不崩）。

## 4. 产物与领域改动

`domain/artifacts.py`：`DesignArtifact` 简化为纯指针（对齐 `ContextArtifact`）：

```python
@dataclass(frozen=True)
class DesignArtifact:
    design_file: str
```

> `change_summary` / `target_files` 原本只被下游桩端口透传、无领域逻辑消费（handlers 只是把 `design` 对象传给 review/impl/delivery 端口），删除不改变任何行为（YAGNI）。

连带更新（均在本仓库内）：
- `adapters/demo.py:DemoDesign.propose` → 返回 `DesignArtifact(design_file=<演示路径或占位>)`。
- SQLite 序列化器中 design 产物的读写字段。
- `webapp/stubs.py:UnavailableStage.propose` 的返回类型注解不变（仍抛 `StageError`），但**不再由生产组合根装配到 designer 位**（见 §5）。
- 引用旧字段 `change_summary`/`target_files` 的现有测试（若有）随之更新。

铁律 4（产物只进不改）由引擎 `add_artifact` 的追加语义保证，本设计不触碰。

## 5. 接入组合根与有界驱动

- **组合根 `webapp/config.py`**：新建
  `designer = ClaudeDesignAdapter(runner=lambda p, c: runner.run(p, c), autodev_home=home)`
  （复用已有 `runner` 与 `home`），把 `StageContext` 第 3 位 `designer` 从 `stub` 换成它；review/execution/verification/delivery 四位仍为 `stub`。
- **有界驱动 `webapp/service.py`**：`RUN` 由 `{INTAKE, TRIAGE, CONTEXT}` 扩为 `{INTAKE, TRIAGE, CONTEXT, DESIGN}`。DESIGN 成功后状态转 `REVIEW`，`REVIEW ∉ RUN` → 驱动自然停住，**绝不触达 review 桩**（沿用越界即停不变式）。
- **自主/门禁联动**（既有逻辑，无需改）：自主开 + ACTIONABLE → 自动跑完 DESIGN 停在 REVIEW；自主关 → 停 CONTEXT_GATE，用户 proceed 后 resume 进入并跑完 DESIGN；咨询 / 低置信 → 仍在 context 阶段 finish 或挂起，不进 DESIGN。
- **安全回归守卫**：现有测试锁死"生产组合根 DESIGN..DELIVERY 5 个端口在沙箱就绪前仍为桩"。本次将该断言**从 5 收窄到 4**（review/execution/verification/delivery），并**新增**断言 `designer` 为 `ClaudeDesignAdapter` 实例。

## 6. 前端（详情页新增「方案」面板）

- **后端投影 `webapp/views.py:view_detail`**：读取 design 产物 `design_file` 指向的 md 文件内容（best-effort，读不到留空/不设），新增 `design_brief` 字段（对齐现有 `context_brief`）。
- **前端**：详情页在「上下文简报」下方新增**「方案」折叠面板**，复用现有 Markdown 渲染管线（`unwrapMarkdownFence` + highlight.js + GitHub 样式）与 `<details>/<summary>` 折叠组件。DESIGN 未产出（无 `design_brief`）时不显示该面板。

## 7. 错误处理（收敛到既有不变式）

| 情形 | 分类 | 结果 |
|------|------|------|
| `claude` 网络/超时 | TRANSIENT | 引擎按 `RetryPolicy` 自动重试（硬上限） |
| `claude` 不可用 / 鉴权失败 | FATAL | 收敛 FAILED（铁律 7） |
| `claude` 其它非零退出 | LOGIC | 收敛 FAILED |
| context 文件 claude 读不到 | —（claude 侧） | 方案照出，不崩 |

## 8. 测试（TDD，先红后绿）

- **契约测试** `tests/adapters/test_design_contract.py`：同一组断言跑 `DemoDesign` 与真实 `ClaudeDesignAdapter`（注入假 runner，离线）——均返回带非空 `design_file` 的 `DesignArtifact`、文件确实落盘、内容含方案小节。
- **适配器单测**：单遍流程、prompt 含 context 文件路径、`StageError` 上抛、持久化路径 `~/.autodev/workitems/<id>/`。
- **`@pytest.mark.live` 冒烟**（`AUTODEV_LIVE=1` 才跑）：真跑 `claude` CLI 端到端出一份方案。
- **组合根守卫更新**：`designer` 为真实、其余 4 端口仍为桩。
- **有界驱动测试**：`RUN` 含 DESIGN，注入假件驱动到 REVIEW 停住、不调 review 桩。
- **序列化测试**：`DesignArtifact` 存取往返 + 旧行兜底。
- **前端 vitest**：详情页方案面板渲染 / 缺省不显示。
- **E2E `tests/e2e/browser_e2e.sh`**：补一条断言——自主开启的落地类工作项推进到 DESIGN 并展示方案面板。

## 9. 文档一致性（CI）

- `CHANGELOG.md` `[Unreleased]` 加条目（改 `src/**` 必需）。
- 切片 2 适配器进度表（ROADMAP）：DesignPort 从 ⬜ 假 → ✅ 真实已落地。
- 若前端引入新组件名触发伪造符号误报，加入 `docs/.doc-allowlist.txt`。

## 10. 首个应写的测试（锁死最脆弱处）

契约测试中"真实 `ClaudeDesignAdapter` 注入假 runner → `propose` 返回的 `DesignArtifact.design_file` 指向的文件确实存在且含方案小节"——一条同时锁死「适配器落盘」与「产物指针语义」，是本迭代最易回归的核心。
