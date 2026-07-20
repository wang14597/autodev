# F3 上下文 ACL（Claude Code 只读调查 + 两遍质检 + 结果落盘）设计

> 日期：2026-07-20
> 状态：设计已在头脑风暴中获认可，待评审后转 writing-plans
> 所属：计划 2（真实 ACL）第 2 个独立大 feature（对应 CONTEXT 阶段）。架构基准见 `docs/architecture/2026-07-15-strategic-direction-and-domain-model.md`。

## 1. 角色与目标

F3 是 `ContextPort.gather` 的真实实现（CONTEXT 阶段）：在 F1 建好的 worktree 里，用 headless Claude Code **只读调查**与需求相关的代码，经**两遍质检**（收集→复核改进）产出一份 **Markdown 上下文结果文件**落盘到平台目录，`ContextArtifact` 只在 DB 里记录该文件的**指针**。它也顺带立起 F5/F2 复用的共享 Claude Code 调用底座。

**在流水线中的位置**：CONTEXT 阶段（`handle_context`）先由 F1 的 `WorkspacePort.provision` 拉出 worktree，再调 `ContextPort.gather` 产出上下文；下游 DESIGN/IMPL（同样在该 worktree 里跑 Claude Code）读取该结果文件。

## 2. 领域改动（ContextArtifact 改为指针）

**动机**：内联大段 `summary` + 长 `relevant_files` 会随 WorkItem 序列化进 SQLite，撑爆 DB 且不利消费。改为"大内容落盘、DB 存指针"。

**改动**：`src/autodev/domain/artifacts.py` 的 `ContextArtifact` 字段：
- 旧：`{workspace_location, workspace_label, relevant_files: tuple[str,...], summary: str}`
- 新：`{workspace_location, workspace_label, context_file: str}`（`context_file` = 结果文件路径；summary 与 relevant_files 移入该文件）

**涟漪（本 feature 一并处理）**：
- `docs/architecture/…domain-model.md`：ContextArtifact 描述更新。
- `src/autodev/adapters/sqlite_repository.py`：ContextArtifact 的 `_artifact_to_dict`/`_from_dict` 改字段。
- `tests/fakes.py` 的 `FakeContext.gather`：返回新字段（假 context_file 路径）。
- 读 ContextArtifact 的处：`_handle_from_context`（引擎，取 workspace_location/label——保留，不受影响）；`handle_context`/`handle_design`（仅透传 artifact，不读被删字段——不受影响）。
- slice-1 中构造 `ContextArtifact(...)` 的测试（test_handlers_front/back、test_engine、e2e 等）：改为新签名。

> 领域契约方法签名不变：`gather(requirement, handle) -> ContextArtifact`；变的是 ContextArtifact 的字段。

## 3. 平台文件目录 `~/.autodev`

约定平台产生的所有文件放在一个可配置的根目录，默认 `~/.autodev`：
- 上下文结果文件：`~/.autodev/workitems/<work_item_id>/context-<discriminator>.md`
- `<discriminator>`：区分同一 WorkItem 多次（回退重跑）收集，避免覆盖上一版指向的文件（呼应"产物只进不改"——每个 ContextArtifact 版本各指各文件）。取一个稳定短标识（如递增序号或 8 位随机 hex；注意实现里不能依赖被禁的时钟/随机 API 处——普通运行代码可用 uuid）。
- **不写进 worktree**：结果文件在 worktree 之外，避免污染目标仓库 / 出现在 git status。
- 根目录可配置（默认 `~/.autodev`；测试指向 tmp）。
- （统一约定：F1 的 mirror/workspaces 目录以后也可默认收到 `~/.autodev` 下；本 feature 不动 F1。）

## 4. 组件

**① ClaudeCodeRunner（共享，`src/autodev/adapters/claude_runner.py`）** — headless Claude 调用底座：
- `run(prompt, cwd, permission_mode="plan", timeout=600) -> str`：在 cwd 跑 `claude -p <prompt> --permission-mode <mode> --bare`，返回 stdout。
- **超时可配、默认 600s**（大项目上下文/编码耗时长）。
- **失败翻译**（同 F1 风格）：超时→TRANSIENT，claude 缺失→FATAL，非零按 stderr 分类（网关/网络→TRANSIENT，鉴权→FATAL，其余→LOGIC）。
- **有界重试辅助**：对 TRANSIENT 失败重试（默认 3 次 + 退避）。
- 鉴权走 ambient 环境（内网 `ANTHROPIC_BASE_URL` 网关），不内建凭证。
- F5/F2 复用（各自仍是独立端口）。

**② ClaudeContextAdapter（`src/autodev/adapters/context_claude.py`）** — 实现 `ContextPort`，构造注入 `runner`（默认真实 ClaudeCodeRunner 的 run）+ `autodev_home`（默认 `~/.autodev`）+ 一个可注入的 `writer`/`id` 生成便于测试。

## 5. `gather(requirement, handle)` 行为（两遍，全内置）

1. **收集遍**：在 `handle.location` 里跑 Claude（plan 只读），prompt 要求输出 JSON `{"relevant_files":[相对 worktree 的路径...], "summary":"..."}`。稳健解析（提取 JSON 对象；解析失败 → 降级：relevant_files=(), summary=原始文本）。调用失败经 runner 的有界重试；耗尽 → 抛 `StageError` 上浮（无上下文=真失败，交引擎 RetryPolicy 重试整阶段）。
2. **确定性守卫①**：过滤 relevant_files 中在 worktree 里**不存在**的路径（抓幻觉）。
3. **复核遍（`_review(first_pass, requirement, handle) -> (files, summary)`，独立可组合）**：第二个 Claude 调用，拿"第一遍结果 + 真实 worktree"核对相关性/完整性/摘要准确性，输出**改进后**的 `{relevant_files, summary}`。
   - 复核调用失败 → runner 有界重试；**重试耗尽 → 降级回第一遍结果**（已有可用上下文，不因质检失败废掉整阶段）。
4. **确定性守卫②**：对改进后的 relevant_files 再过滤不存在路径。
5. **落盘**：adapter（Python，非 Claude）把 `{relevant_files, summary, 元数据(work_item_id/requirement.goal)}` 渲染成 **Markdown**，写到 `~/.autodev/workitems/<work_item_id>/context-<discriminator>.md`。
6. 返回 `ContextArtifact(workspace_location=handle.location, workspace_label=handle.label, context_file=<结果文件路径>)`。

**Claude 只读**：两遍都是 `plan` 模式；写结果文件的是 adapter，Claude 不获写权限。

**为未来 loop 预留**：`_review` 是独立步骤，将来"loop engineering 循环验证直到满意"只需在其外套有界循环；**v1 只跑 1 遍复核**。

## 6. 测试

- **ClaudeContextAdapter 单测（注入假 runner，确定性）**：
  - 收集解析：合法 JSON → 正确；非 JSON → 降级(summary=原文, files=())。
  - 守卫：不存在的路径被过滤（在 tmp worktree 造真实文件验证）。
  - 复核：假 runner 第二次返回改进结果 → 最终 artifact 反映改进；复核 runner 抛错（重试耗尽）→ 降级回第一遍。
  - 落盘：结果文件写到配置的 autodev_home 下正确路径，Markdown 含 summary + relevant_files；`ContextArtifact.context_file` 指向它；文件在 worktree 之外。
  - 收集调用失败 → StageError 上浮。
  - 多次 gather 写到不同文件（不覆盖）。
- **ClaudeCodeRunner 单测（假 subprocess）**：失败翻译（超时/缺失/非零分类）、有界重试、调用参数（`-p/--permission-mode/--bare`、cwd、timeout）正确。
- **live 冒烟（`@pytest.mark.live`，默认跳过）**：真 worktree 真调 claude，断言产出结果文件、非空 summary。
- **端口一致性契约**：真实 ClaudeContextAdapter（注入假 runner）与 `FakeContext` 跑同一组 `ContextPort` 断言（都返回带 context_file/loc/label 的 ContextArtifact，不抛）——顺带保证 FakeContext 已更新为新字段。

## 7. 范围边界与非目标

- F3 交付 ClaudeCodeRunner + ClaudeContextAdapter + ContextArtifact 领域改动及涟漪 + 测试；共享 runner 给 F5/F2。
- 不接入真实运行（在组合根替换 FakeContext 属 F8）；不做 DESIGN/REVIEW（F5）、不做 IMPL（F2）。
- v1 只 1 遍复核（无界循环验证留后续）；并发/锁沿用 F1 的单 worker 前提。
- Claude 纯只读；不建远程仓、不碰 GitLab/飞书。

## 8. 验收标准

- ContextArtifact 改为指针形态，全仓（领域/序列化/fake/测试）一致更新，现有全套测试保持绿。
- ClaudeContextAdapter 两遍质检 + 确定性守卫 + Markdown 落盘 + 指针 artifact，注入假 runner 的单测全通过；复核失败降级、收集失败上浮均有测试。
- ClaudeCodeRunner 失败翻译 + 有界重试 + 调用参数有测试。
- 端口一致性契约证明真实适配器与 FakeContext 行为一致。
- `ruff check . && ruff format --check . && mypy src` 通过。
