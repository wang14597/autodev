import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { WorkItemSummary } from '../api/types'
import { WorkItemCard } from './WorkItemCard'

const item: WorkItemSummary = {
  id: 'wi-42',
  goal: '给网关加限流',
  repo: 'demo-gateway',
  type: null,
  state: 'TRIAGE',
  created_at: '2026-07-22T09:00:00',
  updated_at: '2026-07-22T09:05:00',
}

describe('WorkItemCard', () => {
  it('renders goal, repo, and status, and links to the project-scoped detail page', () => {
    render(
      <MemoryRouter>
        <WorkItemCard item={item} projectId="p-1" />
      </MemoryRouter>,
    )

    expect(screen.getByText('给网关加限流')).toBeInTheDocument()
    expect(screen.getByText('demo-gateway')).toBeInTheDocument()
    expect(screen.getByText('分诊')).toBeInTheDocument()

    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/projects/p-1/workitems/wi-42')
  })
})
