import type { WorkItemState } from '../api/types'

/**
 * Chinese labels for WorkItemState. Note: this is for the *summary* state badge
 * only — per-stage labels in the lifecycle pipeline come from the backend's
 * `StageView.label` and must not be reimplemented here.
 */
export const STATE_LABEL: Record<WorkItemState, string> = {
  INTAKE: '需求录入',
  TRIAGE: '分诊',
  CONTEXT: '上下文',
  DESIGN: '方案',
  REVIEW: '评审',
  IMPL: '开发',
  ACCEPT: '验收',
  VERIFY: '测试',
  SUBMIT_MR: '提交MR',
  DONE: '完成',
  WAIT_HUMAN: '等待人工',
  FAILED: '失败',
}

// Every stage the platform can actually execute, minus the resting states
// (WAIT_HUMAN / DONE / FAILED) where polling would spin forever. Manual tempo
// now routinely parks in DESIGN..SUBMIT_MR waiting for a single 「推进」 click —
// the console must keep polling through those or a multi-minute stage looks dead
// (POST /advance validates synchronously and returns before the stage finishes).
const RUNNING_STATES: ReadonlySet<WorkItemState> = new Set([
  'INTAKE',
  'TRIAGE',
  'CONTEXT',
  'DESIGN',
  'REVIEW',
  'IMPL',
  'ACCEPT',
  'VERIFY',
  'SUBMIT_MR',
])

/** True while the bounded driver is actively auto-advancing this WorkItem. */
export function isRunning(state: WorkItemState): boolean {
  return RUNNING_STATES.has(state)
}

function pad2(n: number): string {
  return n.toString().padStart(2, '0')
}

/**
 * Formats an ISO timestamp for compact display: `HH:MM` for today,
 * `MM-DD HH:MM` otherwise. Returns an em dash for null/invalid input.
 */
export function formatShortTime(iso: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'

  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()

  const time = `${pad2(date.getHours())}:${pad2(date.getMinutes())}`
  if (sameDay) return time
  return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${time}`
}
