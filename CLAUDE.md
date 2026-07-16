# CLAUDE.md

AutoDev —— 围绕 Claude Code 的 AI 研发工作流编排平台：需求→上下文→方案→评审→开发→验收→提 MR，目标是全自动无人值守（按信任梯度放开）。本文件是给 AI agent 的项目记忆，改动本仓库前先读。

## 双平台（最易混淆，务必区分）

- **本仓库（平台源码）= GitHub**：协作走 PR，CI 是 GitHub Actions（`.github/workflows/ci.yml`）。
- **平台运行时对接的目标项目 = GitLab**：拉取/创建仓库、开 MR（经 Delivery ACL）；通知/需求/审批走飞书。
- 因此：描述"向本仓库贡献"用 GitHub/PR 措辞；描述"平台对接目标项目"才用 GitLab/MR。**核心领域层不得出现 git/GitLab/飞书 词汇（见铁律 1）。**

## 架构

六边形（Ports & Adapters）+ 轻量状态机引擎，九阶段流水线。权威基准见 [架构与领域模型](docs/architecture/2026-07-15-strategic-direction-and-domain-model.md)，图见 [diagrams](docs/architecture/diagrams.md)。

- 目录：`src/autodev/domain`（纯领域，仅标准库）、`src/autodev/application`（引擎+九阶段处理器+入口）、`src/autodev/adapters`（仓储/事件总线）、`tests/`。
- 出站端口全集见 `src/autodev/domain/ports.py`；目前只有仓储与事件发布有真实实现，其余为测试假实现，真实 ACL 属 slice 2（见 [ROADMAP](ROADMAP.md)）。
- 关键决策见 [ADR](docs/adr/README.md)。

## 铁律（改代码必须遵守；完整 7 条见架构文档第 2 节）

1. **核心域纯净**：`src/autodev/domain` 不得 import 任何外部系统 SDK，也不得 import `application`/`adapters`。
2. **一切外部经端口/ACL**：外部系统交互只能通过 `ports.py` 定义的端口，实现放 `adapters/`。
3. **失败翻译前置**：外部异常在 ACL 边界翻译成领域失败类型，核心策略不认原始异常。
4. **产物版本化只进不改**：`add_artifact` 只追加新版本，永不覆盖/删除（支撑回退重跑）。
5. **人审是一等状态**：门禁触发挂起为 `WAIT_HUMAN`，由审批事件唤醒；无人值守=关掉该门禁。
6. **支撑域产出领域产物，通用域只搬运**。
7. **一切失败收敛到 FAILED**：所有重试/回退有硬上限，无无限打转。

## 命令

```bash
python3 -m venv venv && . venv/bin/activate && pip install -e '.[dev]'   # 一次性
pytest -q                          # 测试
ruff check . && ruff format --check . && mypy src   # lint / 格式 / 类型
pre-commit install --hook-type pre-push             # 启用本地文档顾问(非阻塞)
```

## 约定

- **TDD**：新功能/修复先写失败测试再实现。
- **Conventional Commits**；提交在非默认分支上进行，不要直接推 main。
- **文档一致性（CI 会卡，见 [设计](docs/superpowers/specs/2026-07-16-doc-consistency-ci-design.md)）**：
  - 不要在文档里用反引号引用代码中**不存在**的符号（会被第 1 层检查判为伪造/漂移）；确属非代码的品牌/概念词加入 `docs/.doc-allowlist.txt`。
  - 正文里易变的计数用 `<!-- fact:KEY -->N` 标记，值须与代码一致；能指向单一真源（如 `ports.py`）就别手抄清单。
  - 改 `src/**`、`scripts/**`、`.github/workflows/**` 需在 `CHANGELOG.md` 加条目，否则 PR 打 `docs:none-needed` 标签或提交尾注 `Docs-Impact: none`。
- **文档位置**：架构基准 `docs/architecture/`；spec/plan `docs/superpowers/`；ADR `docs/adr/`；变更 `CHANGELOG.md`；路线 `ROADMAP.md`。

## 现状

slice 1「行走骨架」已完成并可跑通全生命周期（假适配器）；真实 ACL 适配器 + 端到端冒烟属 slice 2。当前进度与测试规模以 [CHANGELOG](CHANGELOG.md) 和 [ROADMAP](ROADMAP.md) 为准。
