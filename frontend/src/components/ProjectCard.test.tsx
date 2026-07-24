import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { Project } from '../api/types'
import { ProjectCard } from './ProjectCard'

const project: Project = {
  id: 'p-42',
  name: 'demo-gateway',
  repo_source: '/repos/demo-gateway',
  branch: 'main',
  workitem_count: 3,
  created_at: '2026-07-22T09:00:00',
}

describe('ProjectCard', () => {
  it('renders name, repo source, tracked branch, and workitem count, and links to the detail page', () => {
    render(
      <MemoryRouter>
        <ProjectCard project={project} />
      </MemoryRouter>,
    )

    expect(screen.getByText('demo-gateway')).toBeInTheDocument()
    expect(screen.getByText('/repos/demo-gateway')).toBeInTheDocument()
    expect(screen.getByText('main')).toBeInTheDocument()
    expect(screen.getByText('3 个工作项')).toBeInTheDocument()

    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/projects/p-42')
  })
})
