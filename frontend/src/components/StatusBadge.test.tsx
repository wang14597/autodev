import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
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

  it('renders a muted dot for resting states like DESIGN', () => {
    const { container } = render(<StatusBadge state="DESIGN" />)
    expect(container.querySelector('[data-tone="muted"]')).toBeInTheDocument()
  })
})
