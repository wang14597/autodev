# F1 工作区 ACL（git mirror + worktree）设计

> 日期：2026-07-20
> 状态：设计已在头脑风暴中获认可，待评审后转 writing-plans
> 所属：计划 2（真实 ACL）第 1 个独立大 feature。架构基准见 `docs/architecture/2026-07-15-strategic-direction-and-domain-model.md`。

## 1. 角色与目标

F1 为每个 WorkItem 提供**真实、隔离的工作现场**：把逻辑上的目标仓库变成磁盘上一个可读写的 git worktree。它是"在真实代码上干活"的物理载体——`WorkspacePort` 的真实实现，替换目前的 `FakeWorkspace`。

**在流水线中的位置**：CONTEXT 阶段调 `WorkspacePort.provision` 产出 worktree（记入 ContextArtifact 的 workspace_location/workspace_label）；此后 IMPL（执行）在其中改代码、VERIFY（验收）在其中跑测试、SUBMIT_MR（交付）从其分支 push；DONE 调 `cleanup` 回收。它是 F2/F3/F4 的前置地基。

**边界铁律**：F1 只跟 git 打交道，不碰 GitLab API / Claude / 飞书；它是把 git 关在核心域之外的 ACL（铁律 1）。

## 2. 领域契约（已定，不改）

实现 `src/autodev/domain/ports.py` 的 `WorkspacePort`：
- `repo_status(repo: RepoRef) -> RepoStatus`
- `provision(work_item_id: WorkItemId, repo: RepoRef, mode: WorkspaceMode, branch: str) -> WorkspaceHandle`
- `cleanup(handle: WorkspaceHandle) -> None`

值对象：`RepoRef{name}`、`RepoStatus{exists_local, exists_remote}`、`WorkspaceHandle{location, label}`、`WorkspaceMode` = REUSE | FETCH | CREATE。

## 3. 组件与配置

新增适配器（放 `src/autodev/adapters/`）实现 `WorkspacePort`，构造时注入一个配置对象：

```python
# 配置(值对象): 决定"逻辑仓库名 -> 真实 git 地址"与本地缓存布局
class GitWorkspaceConfig:
    repo_map: dict[str, str]   # name -> git URL(显式映射; 测试用 file:// 本地仓)
    mirror_dir: Path           # bare mirror 缓存: <mirror_dir>/<name>.git
    workspaces_dir: Path       # worktree 落地: <workspaces_dir>/<work_item_id>

class GitWorkspaceAdapter:     # implements WorkspacePort
    def __init__(self, config: GitWorkspaceConfig, run=subprocess.run): ...
```

- **仓库解析 = 显式映射表**：`repo_map` 把 name 映射到完整 git URL，逐仓登记。测试映射到 `file://` 本地临时仓，无需真 GitLab、无需凭证。
- **mirror = bare 缓存**：`git clone --mirror` 得到 `<mirror_dir>/<name>.git`；worktree 从 bare mirror `git worktree add` 出。
- **鉴权**：真实 git 操作走运行环境的 ambient git 配置 / SSH；F1 不内建凭证逻辑。测试用 file:// 绕开。
- `run` 注入（默认 `subprocess.run`）以便单测替身/断言命令。

## 4. 行为

**`repo_status(repo)`**
- `exists_local` = `<mirror_dir>/<name>.git` 存在。
- `exists_remote` = name 在 `repo_map` 且 `git ls-remote <url>` 成功（网络/鉴权）；未映射或探测失败 → False。

**`provision(work_item_id, repo, mode, branch)`**
- 按 mode 准备 mirror：
  - **REUSE**：mirror 已在本地 → 直接使用。
  - **FETCH**：mirror 缺 → `git clone --mirror <url>`；已在 → `git remote update`/fetch 刷新。
  - **CREATE**：无远程（全新项目）→ 本地 init 一个空 bare 仓作为该项目 mirror，并造出一个初始提交（空 tree / 占位）使默认分支存在，可据以拉分支。**远程仓创建不在 F1，留给 F6。**
- 拉 worktree：`git -C <mirror> worktree add -b <branch> <workspaces_dir>/<work_item_id> <base>`，base = mirror 默认分支（REUSE/FETCH）或初始提交（CREATE）。
- 返回 `WorkspaceHandle(location=<worktree 路径>, label=<branch>)`。

**`cleanup(handle)`**
- `git worktree remove --force <location>` + 删分支（`git branch -D <label>`）+ `git worktree prune`；**保留 mirror** 复用。

## 5. 两条铁律落点

- **幂等（可重跑，铁律：handler 崩溃后重跑安全）**：`provision` 若目标 worktree 路径已存在且在预期分支上 → 复用而非报错；`cleanup` 对已删对象不报错。
- **失败翻译（铁律 3）**：git 子进程失败在 ACL 边界翻译成领域 `StageError(FailureKind, msg)`，核心策略不见原始 git 错误：
  - 网络/超时（clone/fetch/ls-remote 超时或连接失败）→ `FailureKind.TRANSIENT`
  - 未映射仓库 / 鉴权拒绝 / 配置错 → `FailureKind.FATAL`
  - 其他 git 非零 → `FailureKind.LOGIC`
  - 每个外部 git 调用带超时。

## 6. 测试（F1 无需任何外部凭证，可完整本地测）

- **契约/行为测试**：用本地临时 git 仓作 `file://` 远程 + tmp 的 mirror/workspaces 目录：
  - repo_status：映射且可达 → exists_remote=True；未映射 → False；mirror 在 → exists_local=True。
  - provision REUSE/FETCH/CREATE：worktree 目录建出、在正确分支、内容与远程一致（CREATE 为空仓 + 初始提交）。
  - provision 幂等：重复调用复用同一 worktree，不报错。
  - cleanup：worktree 删除、分支删除、mirror 保留；对已清理对象幂等。
  - 失败翻译：未映射仓库 → `StageError(FATAL)`；模拟 fetch 失败（不可达 URL/超时）→ `StageError(TRANSIENT)`。
- **端口一致性契约测试**：真实的 GitWorkspaceAdapter（待实现）与 `FakeWorkspace` 跑同一组 `WorkspacePort` 断言，保证行为契约一致（"假实现不跑偏"）。

## 7. 范围边界与非目标

- F1 只交付适配器 + 其测试；**把它接进真实运行（在组合根用它替换 `FakeWorkspace`）属于 F8 端到端**，不在 F1。
- **并发**：暂按单 worker——worktree 名以 work_item_id 唯一天然隔离；同一 mirror 的并发 fetch 加锁留后续（spec 注明为已知限制）。
- 不做 GitLab 远程仓创建（F6）、不做真实凭证管理（走 ambient git 环境）。
- 不改任何领域/应用层运行时逻辑，也不改其他适配器。

## 8. 验收标准

- GitWorkspaceAdapter（待实现）实现 `WorkspacePort` 三方法，全部行为测试用本地 git 仓通过。
- 三模式（REUSE/FETCH/CREATE）各有测试；provision/cleanup 幂等有测试；失败翻译（TRANSIENT/FATAL）有测试。
- 端口一致性契约测试证明真实适配器与 `FakeWorkspace` 行为一致。
- 现有全套测试保持绿；`ruff check . && ruff format --check . && mypy src` 通过（注意：mypy 目前 `files=["src"]`，新适配器在 src 内，会被类型检查）。
