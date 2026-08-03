# ReviewPort 真实适配器（方案评审产出最终方案）设计

> 日期：2026-08-03
> 状态：**待定稿**（brainstorming 决策已定，待用户确认后转实现计划）
> 背景：切片 2 已落地 Workspace（F1）/ Context（F3）/ Triage（LLM）/ Design 四个真实适配器，驱动止于 REVIEW，REVIEW 及之后仍为 `UnavailableStage` 桩。本设计把**第 5 个**真实适配器 `ReviewPort` 落地，驱动边界推进到 IMPL 之前。
> 架构基准：[战略方向与领域模型](../../architecture/2026-07-15-strategic-direction-and-domain-model.md)
> 前序：[DesignPort 真实适配器设计](2026-07-29-design-port-real-adapter-design.md)（本设计与其同构）、[手动挡设计](2026-07-30-manual-drive-mode-design.md)（驱动边界与停因分类）

## 0. 已确认决策（brainstorming）

1. **REVIEW 是"精炼"而非"判决"**：输入上下文文档 + 方案文档 + 真实代码，输出一份**最终方案文档**，作为下游（IMPL）的权威输入。不是对 diff 的代码评审——此刻还没有 diff。
2. **拒绝路径保留但收窄到"无法自救"**：评审员的默认职责是修好方案并输出终稿；只有当问题不在方案层面而在上游（需求自相矛盾、上下文缺关键信息、方案方向根本错需重新调研）才判 `approved=False` 触发回退重设计。提示词明确要求优先自救。
3. **只落一份文档**：`final-plan-<rand>.md`，正文即可直接交下游的最终方案，末尾一个「评审说明」小节记录改了什么、为什么。blocking 与 suggestion 条目另存到 `ReviewArtifact` 的 `comments` 供领域判决与 UI 列表。
4. **最终方案经产物指针交给下游**，`ExecutionPort` 签名不动（见 §4 方案对比）。
5. **前端新增「最终方案」面板，与「方案」并列**，可对照初稿与终稿。
6. **连带修掉回退路径的死结**：`DesignPort` 加可选入参传递上一轮评审意见（见 §5）。

## 1. 非目标

- 真实 Execution / Verification / Delivery（仍保持 `UnavailableStage` 桩）。
- 代码评审（评审对象是方案文档；对真实 diff 的评审要等 Execution 产出改动之后）。
- 多轮评审迭代（AI 初稿 → AI 自审 → 人审 → 再改）——属切片 3「Design 与 Review 重流程」。
- 改引擎支持一个阶段落多个产物（见 §4 方案 C 被否原因）。
- `GatePolicy` / `REVIEW_GATE` / 状态机 / `WAIT_HUMAN` 语义一律零改动（铁律 5）。
- `POST /api/workitems/{id}/advance` 的乐观锁（已记录债务，见 ROADMAP「并发与调度」）。

## 2. 流程与状态机（在既有框架内，仅"打通" REVIEW）

```
CONTEXT → 【上下文后决策 · AutonomyPolicy，既有逻辑不变】 → DESIGN(真实, 已落地)
   → REVIEW ← 【本次打通】
        评审通过 + 门禁放行  → 转 IMPL → 停因 NOT_IMPLEMENTED（UI 标「待建设」）
        评审通过 + 门禁要人  → suspend(REVIEW_GATE) → WAIT_HUMAN → 前端批准/拒绝
        评审判定无法自救     → fail(LOGIC) → RetryPolicy 回退 DESIGN（CAP=3 后 FAILED）
```

`handle_review`（`handlers.py`）的门禁与挂起逻辑与本设计语义吻合，无需改动：调端口 → 通过则问 `GatePolicy` → 需人则 `suspend(REVIEW_GATE)`。但**判回退分支不是"无需改动"**：`fail(LOGIC)` 前必须先 `work_item.add_artifact("review", review)` 把被否的评审结论落到工作项上——`Engine.advance()` 的四个结果分支里，`_on_failure`（`src/autodev/application/engine.py`）是唯一不调 `add_artifact` 的一个，若 `handle_review` 不主动补这一手，`artifacts["review"]` 在回退时根本不存在，§5 想打通的 `prior_review` 通道会恒为 `None`（通道建好了但没有任何东西流过去）。这行 `add_artifact` 不能删：`add_artifact` 是 append-only，后续通过的评审会追加为新版本，不会被这份被否的盖住。本次除替换端口实现、扩驱动边界、加投影与前端面板、§5 的回退修复外，还需在 `handle_review` 的回退分支补上这行落产物。

人审恢复路径亦无需改动：`resume_target(REVIEW_GATE, "proceed")` → `S.IMPL`，随后停因为 `NOT_IMPLEMENTED`，前端显示「待建设」+ 灰按钮（手动挡迭代已消除搁浅）。

## 3. 适配器（`adapters/review_claude.py`）

结构镜像 `ClaudeDesignAdapter`：复用 `ClaudeCodeRunner`，在 worktree 内以 `permission-mode plan` 只读跑一遍 `claude`。

```python
class ClaudeReviewAdapter:
    def __init__(self, runner, autodev_home, id_gen=...): ...

    def review(self, design: DesignArtifact, context: ContextArtifact) -> ReviewArtifact:
        raw = self._run_review(design, context)
        approved, comments, body = self._parse(raw)
        path = self._persist(context, body)
        return ReviewArtifact(approved, comments, final_plan_file=str(path))
```

- **提示词**：把 `context.context_file` 与 `design.design_file` 的**绝对路径**写进 prompt（不注入内容，由 CLI 自行读取，与 Design 一致），要求：读两份文档 → 只读核对真实代码（方案里提到的文件是否存在、接口签名是否如其所述、是否与现有架构冲突、是否违反项目约定）→ 输出最终方案。明确要求**优先自救**：能在评审中补全/纠正的问题直接改进到终稿里，不要动辄打回。
- **需求文本不单独传入**：`ReviewPort` 的方法只收方案与上下文两个产物，签名里没有 `Requirement`。这不是缺陷——需求已写在方案文档的头部与上下文文档里，评审员读那两份即可。**因此落盘头部也不能写需求**（下一条）。
- **cwd**：`Path(context.workspace_location)`。
- **落盘**：`~/.autodev/workitems/<id>/final-plan-<id_gen()>.md`，工作项 id 取自 `Path(context.workspace_location).name`（与 Context/Design 一致）。头部只记**分支**与**初稿方案的路径**（供溯源"这份终稿评审的是哪一版初稿"），不记需求。

### 3.1 判决的取出方式：首行哨兵

`ClaudeCodeRunner` 只回 stdout 文本，没有 `LlmTriageAdapter` 那种 `tool_use` 强制 schema 可用。故约定输出格式：

```
REVIEW: APPROVED
- suggestion: <一行说明>
---
（以下为最终方案正文，含末尾「## 评审说明」小节）
```

`REVIEW: BLOCKED` 时以 `- blocking:` 行给出打回理由。解析规则：

| 输入形态 | 判定 |
|---|---|
| 首行 `REVIEW: APPROVED` | `approved=True`，首个 `---` 之后为正文 |
| 首行 `REVIEW: BLOCKED` | `approved=False` |
| 首行是哨兵但**没有** `---` | 哨兵行与意见行之后的剩余全部当正文（缺分隔符不算格式错误） |
| 首行不是哨兵 | **降级**：`approved=True`，整份输出当正文 |
| `approved=True` 但正文 strip 后为空 | 抛 `StageError`（LOGIC）——空方案绝不交下游 |

comments 的采集与 `approved` 无关：扫描哨兵与 `---` 之间的 `- blocking:` / `- suggestion:` 行，**保留前缀原样**收进 `comments`，让 UI 与人一眼看出哪条是拦路的、哪条只是建议。BLOCKED 且正文为空不报错——反正要回退重设计，正文没有用处。

降级方向是有意选的：误判成通过的代价是多走一次 `REVIEW_GATE` 人审；误判成回退的代价是烧掉一次 `RetryPolicy` 的 `CAP` 配额并重跑一次数分钟的 DESIGN。前者明显更轻。

### 3.2 失败翻译（铁律 3 / 7）

`claude` 子进程异常已由 `ClaudeCodeRunner` 翻译成 `StageError`（TRANSIENT / FATAL / LOGIC），适配器**不吞、直接上抛**，交引擎按 `RetryPolicy` 处理：`REVIEW:transient` 重试上限 3、`REVIEW:logic` 回退 DESIGN 上限 3，越界一律收敛 FAILED。适配器自身不加任何重试。落盘 `OSError` 不特殊处理（与 `ClaudeDesignAdapter` 一致），由引擎兜成 unexpected → TRANSIENT。

## 4. 最终方案怎么交到下游（方案对比）

**方案 A（采纳）**：`ReviewArtifact` 加 `final_plan_file: str = ""`（默认值保证旧持久化产物可反序列化，照 `TriageArtifact` 的 `risk` / `signals` 先例）。`handle_impl` 经一个自解释的私有函数取权威方案：评审终稿优先，缺失则退回 DESIGN 初稿。`ExecutionPort` 签名保持 `implement(design: DesignArtifact, handle)` 不变——`DesignArtifact` 本就只是"指向一份方案文档的指针"，装最终方案完全成立。

**方案 B（否）**：改 `ExecutionPort` 签名直接接最终方案。语义更直白，但要连改端口协议、`stubs.py`、`tests/fakes.py`、`demo.py` 与契约测试，而 Execution 的真实实现是下一个迭代项——等于替还没写的代码拍板签名。

**方案 C（否，且不可行）**：REVIEW 落 `design` 键的**新版本**（铁律 4 版本化只进不改），下游与 UI 零改动。但引擎 `_on_success` 对一个 `StageOutcome` 只 `add_artifact` 一次，`approved` / `comments` 便无处可存——而 `handle_review` 的门禁判断与回退判断恰恰需要 `approved`。除非改引擎支持多产物（非目标），出局。

## 5. 连带修复：回退重设计必须带上评审意见

`approved=False` → `RetryPolicy` 回退 DESIGN → 引擎重跑 `handle_design` → 端口方法只收到需求与上下文。**上一轮的 blocking 意见没有任何通道传回设计员**：同样的输入大概率产出同样的方案，招来同样的打回，烧完 `CAP` 收敛 FAILED。

在 `DemoReview` 永远通过的年代这条路不可达，是无人吃过亏的死代码。本次把拒绝变成真的，若照原样发布，等于交付一条**已知走不通**的回退路径。故一并修：

- `DesignPort` 的方法加可选入参 `prior_review`（默认 `None`）。Protocol 结构化匹配要求所有实现同步：真实设计适配器、`FakeDesign`、`DemoDesign`、`UnavailableStage` 各一行。
- `handle_design` 从 `work_item.artifacts.get("review")` 取上一轮评审——存在即说明这是回退重设计——传给端口。
- 真实设计适配器在 prompt 中明确："上一轮方案已被评审否决，理由如下……请针对性重做，不要重复同样的选择。"

## 6. 接线与投影

| 文件 | 改动 |
|---|---|
| `adapters/review_claude.py` | 新增评审适配器（类名见 §3 代码块） |
| `domain/artifacts.py` | `ReviewArtifact` 加 `final_plan_file: str = ""` |
| `adapters/sqlite_repository.py` | 新字段的序列化与反序列化（旧行缺该键时兜底空串），否则重启后指针丢失 |
| `domain/ports.py` | `DesignPort` 方法加 `prior_review` 可选入参 |
| `application/handlers.py` | `handle_impl` 取权威方案；`handle_design` 透传上一轮评审 |
| `adapters/design_claude.py` | 接受并使用 `prior_review` |
| `adapters/demo.py` / `tests/fakes.py` / `webapp/stubs.py` | 签名同步 |
| `webapp/config.py` | 装配真实评审端口；桩只剩 executor / verifier / delivery |
| `webapp/drive.py` | `IMPLEMENTED_STAGES` 加 REVIEW |
| `webapp/views.py` | 新增 `review` 投影（markdown / 路径 / approved / comments） |
| `frontend/` | 「最终方案」面板（复用 `BriefDocument`）+ 意见列表 |

出站端口总数不变（<!-- fact:ports -->11），产物类型数不变（<!-- fact:artifacts -->8）——本次不新增端口或产物类型，只加字段。

`tests/webapp/test_demo_app.py` 的防漂移守卫（断言能力集合与生产组合根"端口是否为桩"逐阶段一致）会在评审端口变真实的那一刻先红，正好充当 TDD 驱动力，不必靠人记着改 `IMPLEMENTED_STAGES`。

## 7. 测试策略（TDD，先红后绿）

- **契约测试** `tests/adapters/test_review_contract.py`：同一套断言分别跑 `DemoReview` 与真实适配器（注入假 runner），照 `test_design_contract.py` 模板。
- **适配器单测** `tests/adapters/test_review_claude.py`：APPROVED / BLOCKED / 无哨兵降级 / APPROVED 且正文为空报 LOGIC / blocking 与 suggestion 分级提取；落盘路径与文件名；提示词含两份文档的绝对路径。
- **live 冒烟**：`@pytest.mark.live`，仅 `AUTODEV_LIVE=1` 时真跑 `claude` CLI。
- **应用层**：`handle_review` 的 BLOCKED → `fail(LOGIC)`；`handle_impl` 取评审终稿而非初稿；**判别性用例**——回退重设计时假设计端口确实收到了上一轮意见（回退到旧实现该用例必失败）。
- **组合根守卫**：防漂移守卫覆盖 REVIEW；安全守卫更新为评审端口真实、executor / verifier / delivery 仍为桩。
- **前端**：最终方案面板与意见列表的 vitest 覆盖。
- **文档一致性**：`CHANGELOG.md` 加条目；ROADMAP 适配器表 `ReviewPort` 改为已实现、驱动边界描述由"止于 REVIEW"更正为"止于 IMPL"。新类名无需进 `docs/.doc-allowlist.txt`——本 spec 只在围栏代码块内提到它（围栏内容不参与伪造符号扫描），而 CHANGELOG 与 ROADMAP 是在类落地之后才写的，届时已是真符号。这样白名单不被稀释，日后重命名仍会被抓到。

## 8. 验收标准

- `pytest -q` 全绿；`ruff check .` / `ruff format --check .` / `mypy src` 通过；前端 typecheck / lint / vitest / build 通过。
- 手工：新建自动挡低风险工作项，能连续跑到 REVIEW 并产出最终方案文档，前端「方案」与「最终方案」两个面板都可展开，随后「实现」行显示「待建设」。
- 手工：高风险工作项在 `REVIEW_GATE` 挂起，前端批准后落到 IMPL 的「待建设」。
- 手工：手动挡工作项在 REVIEW 前停住等「推进」，点一次只跑一个阶段。
