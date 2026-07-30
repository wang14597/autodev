#!/usr/bin/env bash
# 切片 2.1 浏览器端到端(E2E)冒烟：用 agent-browser 驱动确定性演示控制台，验证
#   ① 低风险工作项自动流转到 DONE(无人审)
#   ② 高风险工作项挂起 WAIT_HUMAN 且分诊徽章 risk=HIGH
#   ③ 人审"批准继续"×2(REVIEW→MERGE 纵深防御)后到 DONE
#   ④ 自主开启的落地类工作项驱动经过 DESIGN 阶段，详情页展示「方案」面板
#     (DesignPort 真实/演示适配器产出的方案 Markdown，见 场景③ 断言追加)
#
# 被测系统 = build_demo_app(内存仓储 + 确定性演示适配器 + 真实 Triage/Gate + 放行 dial)。
# 零外部依赖：无网络、无 GitLab、无 live claude、无 token 消耗。
#
# 前置：已 `pip install -e '.[dev,web]'`、`npm i`(frontend)、装好 agent-browser。
# 用法：bash tests/e2e/browser_e2e.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "[1/5] 构建前端 dist(E2E 前置：确保含 TriageBadge/批准按钮)"
( cd frontend && npm run build >/dev/null 2>&1 )

echo "[2/5] 选空闲端口 + 隔离临时 AUTODEV_HOME"
PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
TMP_HOME="$(mktemp -d)"
BASE="http://127.0.0.1:${PORT}"

cleanup() {
  [[ -n "${SERVER_PID:-}" ]] && kill "${SERVER_PID}" 2>/dev/null || true
  agent-browser close --all >/dev/null 2>&1 || true
  rm -rf "${TMP_HOME}" || true
}
trap cleanup EXIT

echo "[3/5] 起演示服务器 ${BASE}"
AUTODEV_HOME="${TMP_HOME}" AUTODEV_FRONTEND_DIST="${ROOT}/frontend/dist" \
  python -m uvicorn autodev.webapp.demo_config:build_demo_app --factory \
  --host 127.0.0.1 --port "${PORT}" >"${TMP_HOME}/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 30); do
  curl -sf "${BASE}/api/projects" >/dev/null 2>&1 && break
  sleep 0.3
done

assert_count() { # selector expected label
  local got; got="$(agent-browser get count "$1" 2>/dev/null | tail -1)"
  [[ "${got}" == "$2" ]] || { echo "  ✗ FAIL: $3 (期望 count=$2, 实得 ${got})"; exit 1; }
  echo "  ✓ $3"
}
assert_has() { # selector needle label
  local got; got="$(agent-browser get text "$1" 2>/dev/null | tr -d '\n')"
  [[ "${got}" == *"$2"* ]] || { echo "  ✗ FAIL: $3 (期望含 '$2', 实得 '${got}')"; exit 1; }
  echo "  ✓ $3"
}

echo "[4/5] 驱动 UI 场景"
agent-browser open "${BASE}" >/dev/null
agent-browser wait --text "创建项目" >/dev/null          # 等 SPA 渲染
# 输入用稳定的 id 选择器(placeholder 文案与 label 不同, 故不用 find placeholder)。
agent-browser fill "#project-name" "demo-e2e" >/dev/null
agent-browser fill "#project-repo" "demo://repo" >/dev/null
# --exact：否则 "创建项目" 会先命中同名标题(子串)而非提交按钮，页面不跳转。
agent-browser find text "创建项目" click --exact >/dev/null
agent-browser wait --text "创建工作项" >/dev/null        # 到项目详情页

back_to_project() {  # 从工作项详情返回项目详情页
  agent-browser find text "← 返回项目" click >/dev/null
  agent-browser wait --text "创建工作项" >/dev/null
}

# 场景 ① 默认关自主 → 收集后停 CONTEXT_GATE → 点「完成(仅收集)」→ DONE
agent-browser fill "#workitem-goal" "fix typo in README" >/dev/null   # 不勾自主
agent-browser find text "创建工作项" click >/dev/null
agent-browser wait --text "人审门禁" >/dev/null
assert_count '[data-testid="approval-panel"]' "1" "场景①：默认关 → 停 CONTEXT_GATE"
assert_count '[data-testid="close-button"]' "1" "场景①：出现「完成(仅收集)」按钮"
agent-browser find testid "close-button" click >/dev/null
agent-browser wait --load networkidle >/dev/null
agent-browser wait --text "生命周期" >/dev/null
assert_count '[data-testid="approval-panel"]' "0" "场景①：完成(仅收集)后到 DONE"

# 场景 ② 开自主 + 咨询意图 → 自动仅收集完成(DONE)，意图徽章=查询咨询
back_to_project
agent-browser fill "#workitem-goal" "how does the login flow work" >/dev/null
agent-browser check "#autonomy-enabled" >/dev/null
agent-browser find text "创建工作项" click >/dev/null
agent-browser wait --text "分诊" >/dev/null
assert_has '[data-testid="triage-intent"]' "查询咨询" "场景②：意图=查询咨询"
assert_count '[data-testid="approval-panel"]' "0" "场景②：咨询类自动仅收集→DONE(无人审)"

# 场景 ③ 开自主 + 低风险落地 → 自动流转到 DONE
back_to_project
agent-browser fill "#workitem-goal" "fix typo in README" >/dev/null
agent-browser check "#autonomy-enabled" >/dev/null
agent-browser find text "创建工作项" click >/dev/null
agent-browser wait --text "分诊" >/dev/null
assert_has '[data-testid="triage-risk"]' "LOW" "场景③：分诊 risk=LOW"
assert_count '[data-testid="approval-panel"]' "0" "场景③：低风险落地自动流转→DONE"
# 自主开启 + 落地类 + 低风险 → FULL_DRIVE 已连带跑过 DESIGN；详情页应展示「方案」面板(DesignPort)。
assert_count 'details[aria-label="方案"]' "1" "场景③：自主落地驱动经过 DESIGN → 展示「方案」面板"
assert_has 'details[aria-label="方案"]' "实现方案" "场景③：「方案」面板含 DesignPort 产出的方案文档内容"

# 场景 ④ 开自主 + 高风险落地 → 靠"风险 HIGH"在 REVIEW 门挡下人审
back_to_project
agent-browser fill "#workitem-goal" "migrate auth and delete old credential tokens" >/dev/null
agent-browser check "#autonomy-enabled" >/dev/null
agent-browser find text "创建工作项" click >/dev/null
agent-browser wait --text "人审门禁" >/dev/null
assert_has '[data-testid="triage-risk"]' "HIGH" "场景④：分诊 risk=HIGH"
assert_count '[data-testid="approval-panel"]' "1" "场景④：高风险落地挂起人审(REVIEW 门)"
assert_count '[data-testid="close-button"]' "0" "场景④：REVIEW 门无「仅收集」键(仅 CONTEXT 门有)"

echo "[5/5] ✓ 全部 E2E 场景通过"
