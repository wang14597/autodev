import { describe, expect, it } from 'vitest'
import { formatShortTime, isRunning, STATE_LABEL } from './workitem'

describe('isRunning', () => {
  it('is true for INTAKE/TRIAGE/CONTEXT', () => {
    expect(isRunning('INTAKE')).toBe(true)
    expect(isRunning('TRIAGE')).toBe(true)
    expect(isRunning('CONTEXT')).toBe(true)
  })

  it('is false for every other state', () => {
    for (const state of [
      'DESIGN',
      'REVIEW',
      'IMPL',
      'ACCEPT',
      'VERIFY',
      'SUBMIT_MR',
      'DONE',
      'WAIT_HUMAN',
      'FAILED',
    ] as const) {
      expect(isRunning(state)).toBe(false)
    }
  })
})

describe('STATE_LABEL', () => {
  it('has a Chinese label for every WorkItemState', () => {
    expect(STATE_LABEL.INTAKE).toBe('需求录入')
    expect(STATE_LABEL.FAILED).toBe('失败')
    expect(STATE_LABEL.WAIT_HUMAN).toBe('等待人工')
    expect(STATE_LABEL.DONE).toBe('完成')
  })
})

describe('formatShortTime', () => {
  it('returns an em dash for null input', () => {
    expect(formatShortTime(null)).toBe('—')
  })

  it('returns an em dash for invalid input', () => {
    expect(formatShortTime('not-a-date')).toBe('—')
  })

  it('formats a same-day timestamp as HH:MM', () => {
    const now = new Date()
    now.setHours(9, 5, 0, 0)
    expect(formatShortTime(now.toISOString())).toBe('09:05')
  })

  it('formats a past-day timestamp as MM-DD HH:MM', () => {
    const past = new Date('2020-03-04T08:07:00')
    expect(formatShortTime(past.toISOString())).toBe('03-04 08:07')
  })
})
