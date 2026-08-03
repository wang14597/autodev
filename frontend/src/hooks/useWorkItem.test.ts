import { describe, expect, it } from 'vitest'
import { pollingInterval, POLL_INTERVAL_MS } from './useWorkItem'

describe('pollingInterval', () => {
  it('polls every 2s for the collect stages (INTAKE/TRIAGE/CONTEXT)', () => {
    expect(pollingInterval('INTAKE')).toBe(POLL_INTERVAL_MS)
    expect(pollingInterval('TRIAGE')).toBe(POLL_INTERVAL_MS)
    expect(pollingInterval('CONTEXT')).toBe(POLL_INTERVAL_MS)
  })

  it('keeps polling through every executable stage manual tempo can rest in', () => {
    // A stage can run for minutes while POST /advance returns immediately (sync
    // validation, async execution) — the console must keep polling or a running
    // stage looks dead until the next manual click.
    for (const state of ['DESIGN', 'REVIEW', 'IMPL', 'ACCEPT', 'VERIFY', 'SUBMIT_MR'] as const) {
      expect(pollingInterval(state)).toBe(POLL_INTERVAL_MS)
    }
  })

  it('stops polling for genuine resting states (terminal / awaiting a human decision)', () => {
    expect(pollingInterval('DONE')).toBe(false)
    expect(pollingInterval('FAILED')).toBe(false)
    expect(pollingInterval('WAIT_HUMAN')).toBe(false)
  })

  it('stops polling when state is not yet known', () => {
    expect(pollingInterval(undefined)).toBe(false)
  })
})
