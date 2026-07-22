import { describe, expect, it } from 'vitest'
import { pollingInterval, POLL_INTERVAL_MS } from './useWorkItem'

describe('pollingInterval', () => {
  it('polls every 2s for running states (INTAKE/TRIAGE/CONTEXT)', () => {
    expect(pollingInterval('INTAKE')).toBe(POLL_INTERVAL_MS)
    expect(pollingInterval('TRIAGE')).toBe(POLL_INTERVAL_MS)
    expect(pollingInterval('CONTEXT')).toBe(POLL_INTERVAL_MS)
  })

  it('stops polling for terminal/resting states', () => {
    expect(pollingInterval('DESIGN')).toBe(false)
    expect(pollingInterval('DONE')).toBe(false)
    expect(pollingInterval('FAILED')).toBe(false)
    expect(pollingInterval('WAIT_HUMAN')).toBe(false)
  })

  it('stops polling when state is not yet known', () => {
    expect(pollingInterval(undefined)).toBe(false)
  })
})
