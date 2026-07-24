import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { vi } from 'vitest'
import {
  ApiError,
  createProject,
  createWorkItem,
  deleteProject,
  getProject,
  getProjectBranches,
  getProjects,
  getWorkItem,
  refreshProject,
  setProjectBranch,
} from './client'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('api/client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('getProjects calls GET /api/projects and returns the Project[] shape', async () => {
    const mock = vi.mocked(fetch)
    const projects = [
      {
        id: 'p-1',
        name: 'demo',
        repo_source: '/repos/demo',
        branch: 'main',
        workitem_count: 3,
        created_at: '2026-07-22T09:00:00',
      },
    ]
    mock.mockResolvedValueOnce(jsonResponse(projects))

    const result = await getProjects()

    expect(result).toEqual(projects)
    const [url, init] = mock.mock.calls[0]
    expect(url).toBe('/api/projects')
    expect(init?.method ?? 'GET').toBe('GET')
  })

  it('createProject POSTs name/repo/branch as JSON and returns {id}', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ id: 'p-2' }))

    const result = await createProject('demo', '/repos/demo', 'develop')

    expect(result).toEqual({ id: 'p-2' })
    const [url, init] = mock.mock.calls[0]
    expect(url).toBe('/api/projects')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual({
      name: 'demo',
      repo: '/repos/demo',
      branch: 'develop',
    })
    const headers = (init?.headers ?? {}) as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('createProject defaults branch to an empty string when omitted', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ id: 'p-3' }))

    await createProject('demo', '/repos/demo')

    const [, init] = mock.mock.calls[0]
    expect(JSON.parse(init?.body as string)).toEqual({
      name: 'demo',
      repo: '/repos/demo',
      branch: '',
    })
  })

  it('getProject calls GET /api/projects/{id} and returns ProjectDetail', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(
      jsonResponse({
        id: 'p-1',
        name: 'demo',
        repo_source: '/repos/demo',
        branch: 'main',
        workitem_count: 1,
        created_at: null,
        workitems: [],
      }),
    )

    const result = await getProject('p-1')

    expect(mock.mock.calls[0][0]).toBe('/api/projects/p-1')
    expect(result.workitems).toEqual([])
  })

  it('refreshProject POSTs to /api/projects/{id}/refresh and returns {branch}', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ branch: 'main' }))

    const result = await refreshProject('p-1')

    expect(result).toEqual({ branch: 'main' })
    const [url, init] = mock.mock.calls[0]
    expect(url).toBe('/api/projects/p-1/refresh')
    expect(init?.method).toBe('POST')
  })

  it('getProjectBranches calls GET /api/projects/{id}/branches and returns string[]', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse(['develop', 'main']))

    const result = await getProjectBranches('p-1')

    expect(result).toEqual(['develop', 'main'])
    const [url, init] = mock.mock.calls[0]
    expect(url).toBe('/api/projects/p-1/branches')
    expect(init?.method ?? 'GET').toBe('GET')
  })

  it('getProjectBranches resolves to [] when the project has no branches', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse([]))

    const result = await getProjectBranches('p-1')

    expect(result).toEqual([])
  })

  it('setProjectBranch POSTs {branch} to /api/projects/{id}/branch and returns {branch}', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ branch: 'develop' }))

    const result = await setProjectBranch('p-1', 'develop')

    expect(result).toEqual({ branch: 'develop' })
    const [url, init] = mock.mock.calls[0]
    expect(url).toBe('/api/projects/p-1/branch')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual({ branch: 'develop' })
    const headers = (init?.headers ?? {}) as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('setProjectBranch throws ApiError 400 for an invalid/empty branch', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ detail: '分支不存在。' }, 400))

    await expect(setProjectBranch('p-1', 'nope')).rejects.toMatchObject({
      name: 'ApiError',
      status: 400,
      detail: '分支不存在。',
    })
  })

  it('setProjectBranch throws ApiError 404 for an unknown project', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ detail: 'project not found' }, 404))

    await expect(setProjectBranch('nope', 'main')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      detail: 'project not found',
    })
  })

  it('deleteProject DELETEs /api/projects/{id} and resolves to undefined', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ deleted: true }))

    const result = await deleteProject('p-1')

    expect(result).toBeUndefined()
    const [url, init] = mock.mock.calls[0]
    expect(url).toBe('/api/projects/p-1')
    expect(init?.method).toBe('DELETE')
  })

  it('createWorkItem POSTs goal as JSON to /api/projects/{id}/workitems', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ id: 'wi-2' }))

    const result = await createWorkItem('p-1', '加限流')

    expect(result).toEqual({ id: 'wi-2' })
    const [url, init] = mock.mock.calls[0]
    expect(url).toBe('/api/projects/p-1/workitems')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual({ goal: '加限流' })
    const headers = (init?.headers ?? {}) as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('getWorkItem calls GET /api/workitems/{id}', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(
      jsonResponse({
        id: 'wi-1',
        goal: 'g',
        repo: 'demo',
        type: null,
        state: 'INTAKE',
        created_at: null,
        updated_at: null,
        stages: [],
        context: null,
        failure: null,
      }),
    )

    const result = await getWorkItem('wi-1')

    expect(mock.mock.calls[0][0]).toBe('/api/workitems/wi-1')
    expect(result.id).toBe('wi-1')
  })

  it('throws ApiError with status and detail on non-2xx responses', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ detail: '项目名和仓库都要填。' }, 400))

    await expect(createProject('', '')).rejects.toMatchObject(
      new ApiError(400, '项目名和仓库都要填。'),
    )
  })

  it('throws ApiError with status 404 for an unknown project', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ detail: 'project not found' }, 404))

    await expect(getProject('nope')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      detail: 'project not found',
    })
  })
})
