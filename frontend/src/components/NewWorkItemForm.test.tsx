import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import { NewWorkItemForm } from './NewWorkItemForm'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof client>('../api/client')
  return {
    ...actual,
    createWorkItem: vi.fn(),
  }
})

function renderForm() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NewWorkItemForm projectId="p-1" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('NewWorkItemForm', () => {
  beforeEach(() => {
    vi.mocked(client.createWorkItem).mockReset()
  })

  it('shows an inline validation error and does not submit when the goal is empty', async () => {
    const user = userEvent.setup()
    renderForm()

    await user.click(screen.getByRole('button', { name: '创建工作项' }))

    expect(await screen.findByText('需求不能为空。')).toBeInTheDocument()
    expect(client.createWorkItem).not.toHaveBeenCalled()
  })

  it('submits the goal against the given project id when filled', async () => {
    vi.mocked(client.createWorkItem).mockResolvedValue({ id: 'wi-1' })
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('需求'), '加限流')
    await user.click(screen.getByRole('button', { name: '创建工作项' }))

    expect(client.createWorkItem).toHaveBeenCalledWith('p-1', '加限流', false)
  })

  it('surfaces a server-side error from the mutation', async () => {
    vi.mocked(client.createWorkItem).mockRejectedValue(new client.ApiError(400, '需求不能为空。'))
    const user = userEvent.setup()
    renderForm()

    await user.type(screen.getByLabelText('需求'), '加限流')
    await user.click(screen.getByRole('button', { name: '创建工作项' }))

    expect(await screen.findByText('需求不能为空。')).toBeInTheDocument()
  })
})
