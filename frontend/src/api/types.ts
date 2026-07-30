/**
 * DTOs mirroring `src/autodev/webapp/views.py` on the backend. Keep field names
 * and shapes in lockstep with that module — it is the single source of truth.
 */

export type WorkItemState =
  | 'INTAKE'
  | 'TRIAGE'
  | 'CONTEXT'
  | 'DESIGN'
  | 'REVIEW'
  | 'IMPL'
  | 'ACCEPT'
  | 'VERIFY'
  | 'SUBMIT_MR'
  | 'DONE'
  | 'WAIT_HUMAN'
  | 'FAILED'

export interface WorkItemSummary {
  id: string
  goal: string
  repo: string
  type: string | null
  state: WorkItemState
  autonomy_enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export type StageStatus = 'done' | 'current' | 'pending' | 'blocked'

export interface StageView {
  key: string
  label: string
  status: StageStatus
}

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH'

export type TriageIntent = 'ACTIONABLE' | 'CONSULTATION'

export interface TriageView {
  level: string
  confidence: number
  risk: RiskLevel
  signals: string[]
  intent: TriageIntent
}

export type GatePoint = 'CONTEXT_GATE' | 'REVIEW_GATE' | 'MERGE_GATE'

export interface WorkItemDetail extends WorkItemSummary {
  stages: StageView[]
  context: { markdown: string; context_file: string } | null
  design: { markdown: string; design_file: string } | null
  failure: { reason: string } | null
  triage: TriageView | null
  pending_gate: GatePoint | null
  collect_only: boolean
}

export interface Project {
  id: string
  name: string
  repo_source: string
  branch: string
  workitem_count: number
  created_at: string | null
}

export interface ProjectDetail extends Project {
  workitems: WorkItemSummary[]
}
