import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'

describe('typed API client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('unwraps the data envelope and adds a request id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { projects: [], frontend_modes: ['planned', 'conversational'] } }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const result = await api.bootstrap()
    expect(result.projects).toEqual([])
    expect(fetchMock.mock.calls[0][1].headers['X-Request-Id']).toBeTruthy()
  })

  it('builds usage breakdown and multipart batch import requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { dimension: 'operation', rows: [] } }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await api.usageBreakdown('operation', 'project-1', 'story-1')
    expect(fetchMock.mock.calls[0][0]).toContain('/usage/breakdown?dimension=operation')
    await api.uploadIngestionBatch('project-1', 'story-1', [new File(['notes'], 'notes.txt', { type: 'text/plain' })])
    const batchInit = fetchMock.mock.calls[1][1]
    expect(batchInit.body).toBeInstanceOf(FormData)
    expect(batchInit.headers['X-NovelForge-Client']).toBe('vue')
  })

  it('omits the empty content cursor required by the integer API contract', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { items: [], next_cursor: '40', total: 0 } }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.content('project-1', 'story-1')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/projects/project-1/content?story_id=story-1&page_size=40')

    await api.content('project-1', 'story-1', '40')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/projects/project-1/content?story_id=story-1&cursor=40&page_size=40')
  })

  it('replays bounded operation events after an SSE disconnect', async () => {
    const encoder = new TextEncoder()
    let sent = false
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (sent) {
          controller.error(new Error('fixture disconnect'))
          return
        }
        sent = true
        controller.enqueue(encoder.encode('id: 1\nevent: operation.started\ndata: {"operation_id":"op_fixture","status":"running"}\n\n'))
        controller.enqueue(encoder.encode('id: 2\nevent: delta\ndata: {"text":"半句"}\n\n'))
      },
    })
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/operations/op_fixture/events')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: { operation_id: 'op_fixture', events: [{ id: 3, event: 'done', data: { operation_id: 'op_fixture', result: { content: '完成' } } }] } }) })
      }
      return Promise.resolve({ ok: true, body: stream })
    })
    vi.stubGlobal('fetch', fetchMock)
    const events: string[] = []
    await api.streamTurn('project-1', 'story-1', 'session-1', { user_message: '继续' }, (event) => events.push(event))
    expect(events).toEqual(['operation.started', 'delta', 'done'])
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1][0]).toContain('/operations/op_fixture/events?after=2')
  })

  it('keeps branch identity separate from source worldline and binds a story copy explicitly', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { branches: [{ branch_id: 'branch_main_s1', name: '主线', status: 'active', source_worldline_id: 'canon-a' }] } }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await api.branches('project-1', 'story-1')
    expect(fetchMock.mock.calls[0][0]).toContain('/projects/project-1/stories/story-1/branches')

    await api.forkBranch('project-1', 'story-1', 'branch_main_s1', { name: '获救线', fork_fragment_id: 'fragment-7' })
    expect(fetchMock.mock.calls[1][1].body).toContain('fragment-7')

    await api.bindReferenceLibrary('project-1', 'story-1', 'library-a', { release_id: 'release-2', branch_id: 'branch_child', idempotency_key: 'op-1' })
    expect(fetchMock.mock.calls[2][0]).toContain('/reference-libraries/library-a/bindings')
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ release_id: 'release-2', branch_id: 'branch_child', idempotency_key: 'op-1' })
  })

  it('resolves an ambiguous pending entity in the selected story branch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { candidate: { canonical_name: '林越' }, resolved: true } }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await api.resolvePendingEntity('project-1', 'pending-7', 'entity-2', 'story-1', 'branch-child')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/projects/project-1/knowledge/pending/pending-7/resolve-entity?story_id=story-1&branch_id=branch-child')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ target_entity_id: 'entity-2' })
  })
})
