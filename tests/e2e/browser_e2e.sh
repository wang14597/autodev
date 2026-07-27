#!/usr/bin/env bash
# 切片 2.1 浏览器端到端(E2E)冒烟：用 agent-browser 驱动确定性演示控制台，验证
#   ① 低风险工作项自动流转到 DONE(无人审)
#   ② 高风险工作项挂起 WAIT_HUMAN 且分诊徽章 risk=HIGH
#   ③ 人审"批准继续"×2(REVIEW→MERGE 纵深防御)后到 DONE
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

# 场景 ① 低风险 → DONE
agent-browser fill "#workitem-goal" "fix typo in README" >/dev/null
agent-browser find text "创建工作项" click >/dev/null
agent-browser wait --text "分诊" >/dev/null              # 到工作项详情页
assert_has '[data-testid="triage-risk"]' "LOW" "场景①：分诊 risk=LOW"
assert_count '[data-testid="approval-panel"]' "0" "场景①：无人审门(DONE 自动流转)"

# 场景 ② 高风险 → WAIT_HUMAN
agent-browser find text "← 返回项目" click >/dev/null
agent-browser wait --text "创建工作项" >/dev/null
agent-browser fill "#workitem-goal" "migrate auth to new credential store and delete old tokens" >/dev/null
agent-browser find text "创建工作项" click >/dev/null
agent-browser wait --text "人审门禁" >/dev/null          # 挂起面板出现
assert_has '[data-testid="triage-risk"]' "HIGH" "场景②：分诊 risk=HIGH"
assert_count '[data-risk="HIGH"]' "1" "场景②：HIGH 风险徽章"
assert_count '[data-testid="approval-panel"]' "1" "场景②：挂起人审门(WAIT_HUMAN)"

# 场景 ③ 批准×2 → DONE(高风险在 REVIEW 与 MERGE 两门都挂起)
agent-browser find testid "approve-button" click >/dev/null
agent-browser wait --load networkidle >/dev/null
agent-browser wait --text "人审门禁" >/dev/null          # MERGE 门再次挂起
assert_count '[data-testid="approval-panel"]' "1" "场景③：首次批准后于 MERGE 门再挂起(纵深防御)"
agent-browser find testid "approve-button" click >/dev/null
agent-browser wait --load networkidle >/dev/null
agent-browser wait --text "生命周期" >/dev/null          # 详情仍在, 但人审面板消失
assert_count '[data-testid="approval-panel"]' "0" "场景③：二次批准后到 DONE"

echo "[5/5] ✓ 全部 E2E 场景通过"
