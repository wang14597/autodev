import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { WorkItemState } from '../api/types'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('shows the Chinese label for the state', () => {
    render(<StatusBadge state="CONTEXT" />)
    expect(screen.getByText('上下文')).toBeInTheDocument()
  })

  it('renders a running-tone dot for active states', () => {
    const { container } = render(<StatusBadge state="TRIAGE" />)
    expect(container.querySelector('[data-tone="running"]')).toBeInTheDocument()
  })

  it('renders a done-tone dot for DONE', () => {
    const { container } = render(<StatusBadge state="DONE" />)
    expect(container.querySelector('[data-tone="done"]')).toBeInTheDocument()
  })

  it('renders an error-tone dot for FAILED', () => {
    const { container } = render(<StatusBadge state="FAILED" />)
    expect(container.querySelector('[data-tone="error"]')).toBeInTheDocument()
  })

  it('renders a running-tone (amber) dot for WAIT_HUMAN', () => {
    const { container } = render(<StatusBadge state="WAIT_HUMAN" />)
    expect(container.querySelector('[data-tone="running"]')).toBeInTheDocument()
    expect(screen.getByText('等待人工')).toBeInTheDocument()
  })

  it('renders a running-tone dot for DESIGN (manual tempo now rests there while it may still execute)', () => {
    const { container } = render(<StatusBadge state="DESIGN" />)
    expect(container.querySelector('[data-tone="running"]')).toBeInTheDocument()
  })

  it('falls back to a muted dot for a state outside the currently known set', () => {
    // Every real WorkItemState is handled explicitly by toneFor; "muted" is a
    // defensive fallback for states added later. Cast to exercise that branch.
    const { container } = render(
      <StatusBadge state={'SOMETHING_FUTURE' as unknown as WorkItemState} />,
    )
    expect(container.querySelector('[data-tone="muted"]')).toBeInTheDocument()
  })
})
