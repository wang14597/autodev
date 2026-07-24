import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import type { Project } from '../api/types'
import { ProjectHeader } from './ProjectHeader'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof client>('../api/client')
  return {
    ...actual,
    deleteProject: vi.fn(),
    refreshProject: vi.fn(),
    getProjectBranches: vi.fn(),
    setProjectBranch: vi.fn(),
  }
})

const project: Project = {
  id: 'p-1',
  name: 'demo',
  repo_source: '/repos/demo',
  branch: 'main',
  workitem_count: 2,
  created_at: null,
}

function renderHeader() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ProjectHeader project={project} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ProjectHeader', () => {
  beforeEach(() => {
    vi.mocked(client.deleteProject).mockReset().mockResolvedValue(undefined)
    vi.mocked(client.refreshProject).mockReset().mockResolvedValue({ branch: 'main' })
    vi.mocked(client.getProjectBranches).mockReset().mockResolvedValue(['develop', 'main'])
    vi.mocked(client.setProjectBranch).mockReset().mockResolvedValue({ branch: 'develop' })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the project identity: name, repo source, and a branch select with the current branch', async () => {
    renderHeader()

    expect(screen.getByText('demo')).toBeInTheDocument()
    expect(screen.getByText('/repos/demo')).toBeInTheDocument()

    const select = await screen.findByLabelText('默认分支')
    expect(select).toHaveValue('main')
    expect(screen.getByRole('option', { name: 'main' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'develop' })).toBeInTheDocument()
  })

  it('falls back to plain text while the branch list is loading', () => {
    vi.mocked(client.getProjectBranches).mockReturnValue(new Promise(() => {}))
    renderHeader()

    expect(screen.queryByLabelText('默认分支')).not.toBeInTheDocument()
    expect(screen.getByText('main')).toBeInTheDocument()
  })

  it('always offers the current branch as an option even if the fetched list omits it', async () => {
    vi.mocked(client.getProjectBranches).mockResolvedValue(['develop', 'staging'])
    renderHeader()

    const select = await screen.findByLabelText('默认分支')
    expect(select).toHaveValue('main')
    expect(screen.getByRole('option', { name: 'main' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'develop' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'staging' })).toBeInTheDocument()
  })

  it('calls setProjectBranch with the newly chosen branch', async () => {
    const user = userEvent.setup()
    renderHeader()

    const select = await screen.findByLabelText('默认分支')
    await user.selectOptions(select, 'develop')

    expect(client.setProjectBranch).toHaveBeenCalledWith('p-1', 'develop')
  })

  it('shows an inline error when switching the branch fails', async () => {
    vi.mocked(client.setProjectBranch).mockRejectedValue(new client.ApiError(400, '分支不存在。'))
    const user = userEvent.setup()
    renderHeader()

    const select = await screen.findByLabelText('默认分支')
    await user.selectOptions(select, 'develop')

    expect(await screen.findByText(/切换分支失败/)).toBeInTheDocument()
  })

  it('calls refreshProject when the refresh button is clicked', async () => {
    const user = userEvent.setup()
    renderHeader()

    await user.click(screen.getByRole('button', { name: '刷新' }))

    expect(client.refreshProject).toHaveBeenCalledWith('p-1')
  })

  it('does not delete when the confirm dialog is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    renderHeader()

    await user.click(screen.getByRole('button', { name: '删除项目' }))

    expect(window.confirm).toHaveBeenCalled()
    expect(client.deleteProject).not.toHaveBeenCalled()
  })

  it('deletes the project once the confirm dialog is accepted', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderHeader()

    await user.click(screen.getByRole('button', { name: '删除项目' }))

    expect(client.deleteProject).toHaveBeenCalledWith('p-1')
  })
})
