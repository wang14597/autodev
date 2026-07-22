import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createWorkItem, getProjects, getWorkItem, listWorkItems } from './client'

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

  it('getProjects calls GET /api/projects and returns the list', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse(['demo', 'platform']))

    const result = await getProjects()

    expect(result).toEqual(['demo', 'platform'])
    const [url, init] = mock.mock.calls[0]
    expect(url).toBe('/api/projects')
    expect(init?.method ?? 'GET').toBe('GET')
  })

  it('listWorkItems calls GET /api/workitems', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse([]))

    await listWorkItems()

    expect(mock.mock.calls[0][0]).toBe('/api/workitems')
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

  it('createWorkItem POSTs goal/repo as JSON and returns {id}', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ id: 'wi-2' }))

    const result = await createWorkItem('加限流', 'demo')

    expect(result).toEqual({ id: 'wi-2' })
    const [url, init] = mock.mock.calls[0]
    expect(url).toBe('/api/workitems')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(init?.body as string)).toEqual({ goal: '加限流', repo: 'demo' })
    const headers = (init?.headers ?? {}) as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('throws ApiError with status and detail on non-2xx responses', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ detail: '需求和项目都要填。' }, 400))

    await expect(createWorkItem('', '')).rejects.toMatchObject(
      new ApiError(400, '需求和项目都要填。'),
    )
  })

  it('throws ApiError with status 404 for missing work items', async () => {
    const mock = vi.mocked(fetch)
    mock.mockResolvedValueOnce(jsonResponse({ detail: 'work item not found' }, 404))

    await expect(getWorkItem('nope')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      detail: 'work item not found',
    })
  })
})
