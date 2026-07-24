import type { Project, ProjectDetail, WorkItemDetail } from './types'

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

export function getProjects(): Promise<Project[]> {
  return request<Project[]>('/api/projects')
}

export function createProject(name: string, repo: string): Promise<{ id: string }> {
  return request<{ id: string }>('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ name, repo }),
  })
}

export function getProject(id: string): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/api/projects/${encodeURIComponent(id)}`)
}

export function refreshProject(id: string): Promise<{ default_branch: string | null }> {
  return request<{ default_branch: string | null }>(
    `/api/projects/${encodeURIComponent(id)}/refresh`,
    { method: 'POST' },
  )
}

export async function deleteProject(id: string): Promise<void> {
  await request<{ deleted: boolean }>(`/api/projects/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}

export function createWorkItem(projectId: string, goal: string): Promise<{ id: string }> {
  return request<{ id: string }>(`/api/projects/${encodeURIComponent(projectId)}/workitems`, {
    method: 'POST',
    body: JSON.stringify({ goal }),
  })
}

export function getWorkItem(id: string): Promise<WorkItemDetail> {
  return request<WorkItemDetail>(`/api/workitems/${encodeURIComponent(id)}`)
}
