import { describe, expect, it } from 'vitest'
import { workItemsRefetchInterval } from './useWorkItems'
import type { WorkItemSummary } from '../api/types'

function item(state: WorkItemSummary['state']): WorkItemSummary {
  return {
    id: 'x',
    goal: 'g',
    repo: 'r',
    type: null,
    state,
    created_at: null,
    updated_at: null,
  }
}

describe('workItemsRefetchInterval', () => {
  it('polls while any item is running', () => {
    expect(workItemsRefetchInterval([item('DONE'), item('CONTEXT')])).toBe(3000)
  })

  it('stops when all items are in a resting state', () => {
    expect(workItemsRefetchInterval([item('DESIGN'), item('FAILED'), item('DONE')])).toBe(false)
  })

  it('stops for empty or undefined lists', () => {
    expect(workItemsRefetchInterval([])).toBe(false)
    expect(workItemsRefetchInterval(undefined)).toBe(false)
  })
})
