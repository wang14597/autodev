import { describe, expect, it } from 'vitest'
import { projectRefetchInterval } from './useProject'
import type { ProjectDetail, WorkItemSummary } from '../api/types'

function workitem(state: WorkItemSummary['state']): WorkItemSummary {
  return {
    id: 'x',
    goal: 'g',
    repo: 'demo',
    type: null,
    state,
    created_at: null,
    updated_at: null,
  }
}

function detail(workitems: WorkItemSummary[]): ProjectDetail {
  return {
    id: 'p-1',
    name: 'demo',
    repo_source: '/repos/demo',
    default_branch: 'main',
    workitem_count: workitems.length,
    created_at: null,
    workitems,
  }
}

describe('projectRefetchInterval', () => {
  it('polls every 3s while any workitem is running', () => {
    expect(projectRefetchInterval(detail([workitem('DONE'), workitem('CONTEXT')]))).toBe(3000)
  })

  it('stops polling once every workitem is resting', () => {
    expect(projectRefetchInterval(detail([workitem('DESIGN'), workitem('FAILED')]))).toBe(false)
  })

  it('stops polling for an empty workitem list or undefined detail', () => {
    expect(projectRefetchInterval(detail([]))).toBe(false)
    expect(projectRefetchInterval(undefined)).toBe(false)
  })
})
