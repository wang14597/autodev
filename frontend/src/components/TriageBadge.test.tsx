import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TriageBadge } from './TriageBadge'

const HIGH = {
  level: 'SMALL_CHANGE',
  confidence: 0.7,
  risk: 'HIGH' as const,
  signals: ['keyword:delete', 'keyword:credential'],
  intent: 'ACTIONABLE' as const,
}

describe('TriageBadge', () => {
  it('shows the stable risk token (for E2E assertions)', () => {
    render(<TriageBadge triage={HIGH} />)
    expect(screen.getByTestId('triage-risk')).toHaveTextContent('HIGH')
  })

  it('tags the risk level via data-risk for tone styling', () => {
    const { container } = render(<TriageBadge triage={HIGH} />)
    expect(container.querySelector('[data-risk="HIGH"]')).toBeInTheDocument()
  })

  it('renders explainable signals', () => {
    render(<TriageBadge triage={HIGH} />)
    expect(screen.getByText(/keyword:delete/)).toBeInTheDocument()
  })

  it('renders a low-risk badge without signals gracefully', () => {
    const low = {
      level: 'SMALL_CHANGE',
      confidence: 0.9,
      risk: 'LOW' as const,
      signals: [],
      intent: 'ACTIONABLE' as const,
    }
    const { container } = render(<TriageBadge triage={low} />)
    expect(container.querySelector('[data-risk="LOW"]')).toBeInTheDocument()
    expect(screen.getByTestId('triage-risk')).toHaveTextContent('LOW')
  })

  it('shows the intent label', () => {
    const consult = {
      level: 'SMALL_CHANGE',
      confidence: 0.9,
      risk: 'LOW' as const,
      signals: [],
      intent: 'CONSULTATION' as const,
    }
    render(<TriageBadge triage={consult} />)
    expect(screen.getByTestId('triage-intent')).toHaveTextContent('查询咨询')
  })
})
