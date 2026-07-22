import type { WorkItemDetail, WorkItemSummary } from './types'

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body && typeof body.detail === 'string') {
        detail = body.detail
      }
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new ApiError(response.status, detail)
  }

  return (await response.json()) as T
}

export function getProjects(): Promise<string[]> {
  return request<string[]>('/api/projects')
}

export function listWorkItems(): Promise<WorkItemSummary[]> {
  return request<WorkItemSummary[]>('/api/workitems')
}

export function getWorkItem(id: string): Promise<WorkItemDetail> {
  return request<WorkItemDetail>(`/api/workitems/${encodeURIComponent(id)}`)
}

export function createWorkItem(goal: string, repo: string): Promise<{ id: string }> {
  return request<{ id: string }>('/api/workitems', {
    method: 'POST',
    body: JSON.stringify({ goal, repo }),
  })
}
