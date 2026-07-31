import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { StageView } from '../api/types'
import { LifelinePipeline } from './LifelinePipeline'

const stages: StageView[] = [
  { key: 'INTAKE', label: '需求录入', status: 'done' },
  { key: 'TRIAGE', label: '分诊', status: 'done' },
  { key: 'CONTEXT', label: '上下文', status: 'current' },
  { key: 'DESIGN', label: '方案', status: 'blocked' },
  { key: 'REVIEW', label: '评审', status: 'blocked' },
]

describe('LifelinePipeline', () => {
  it('tags every blocked stage with 待建设', () => {
    render(<LifelinePipeline stages={stages} state="CONTEXT" />)
    expect(screen.getAllByText('待建设')).toHaveLength(2)
  })

  it('marks the current stage amber and shows a sonar ping while running', () => {
    const { container } = render(<LifelinePipeline stages={stages} state="CONTEXT" />)
    const currentDot = container.querySelector('[data-status="current"]')
    expect(currentDot).toBeInTheDocument()
    expect(currentDot?.querySelector('[class*="sonar"]')).toBeInTheDocument()
  })

  it('does not sonar the current stage once the WorkItem has come to rest', () => {
    // DESIGN is no longer a resting state for this purpose — manual tempo now
    // routinely parks there awaiting a 「推进」 click while the stage may still
    // be executing, so it must keep sonar-ing. WAIT_HUMAN (an open gate) is the
    // genuine rest: nothing is running until a human decides.
    const restingStages: StageView[] = [
      { key: 'INTAKE', label: '需求录入', status: 'done' },
      { key: 'TRIAGE', label: '分诊', status: 'done' },
      { key: 'CONTEXT', label: '上下文', status: 'current' },
      { key: 'DESIGN', label: '方案', status: 'pending' },
    ]
    const { container } = render(<LifelinePipeline stages={restingStages} state="WAIT_HUMAN" />)
    const currentDot = container.querySelector('[data-status="current"]')
    expect(currentDot?.querySelector('[class*="sonar"]')).not.toBeInTheDocument()
  })

  it('renders a checkmark for done stages', () => {
    render(<LifelinePipeline stages={stages} state="CONTEXT" />)
    expect(screen.getAllByText('✓')).toHaveLength(2)
  })
})
