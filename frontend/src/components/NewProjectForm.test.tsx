import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import { NewProjectForm } from './NewProjectForm'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof client>('../api/client')
  return {
    ...actual,
    createProject: vi.fn(),
  }
})

function renderForm() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NewProjectForm />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('NewProjectForm', () => {
  beforeEach(() => {
    vi.mocked(client.createProject).mockReset()
  })

  it('shows an inline validation error and does not submit when name or repo is empty', async () => {
    const user = userEvent.setup()
    renderForm()

    await user.click(screen.getByRole('button', { name: '创建项目' }))

    expect(await screen.findByText('项目名和仓库都要填。')).toBeInTheDocument()
    expect(client.createProject).not.toHaveBeenCalled()
  })

  it('submits name and repo with an empty branch when the branch field is left blank', async () => {
    vi.mocked(client.createProject).mockResolvedValue({ id: 'p-1' })
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('项目名'), 'demo')
    await user.type(screen.getByLabelText('仓库地址或本地 git 路径'), '/repos/demo')
    await user.click(screen.getByRole('button', { name: '创建项目' }))

    expect(client.createProject).toHaveBeenCalledWith('demo', '/repos/demo', '')
  })

  it('submits the trimmed branch when one is filled in', async () => {
    vi.mocked(client.createProject).mockResolvedValue({ id: 'p-1' })
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('项目名'), 'demo')
    await user.type(screen.getByLabelText('仓库地址或本地 git 路径'), '/repos/demo')
    await user.type(screen.getByLabelText('默认分支'), ' develop ')
    await user.click(screen.getByRole('button', { name: '创建项目' }))

    expect(client.createProject).toHaveBeenCalledWith('demo', '/repos/demo', 'develop')
  })

  it('surfaces a server-side error from the mutation', async () => {
    vi.mocked(client.createProject).mockRejectedValue(new client.ApiError(400, '仓库不存在。'))
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('项目名'), 'demo')
    await user.type(screen.getByLabelText('仓库地址或本地 git 路径'), '/repos/demo')
    await user.click(screen.getByRole('button', { name: '创建项目' }))

    expect(await screen.findByText('仓库不存在。')).toBeInTheDocument()
  })
})
