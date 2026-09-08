import { nextTick, reactive } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ResearchView from './ResearchView.vue'

const deferred = <T>() => {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

const apiMock = vi.hoisted(() => ({
  ingestionWorkbench: vi.fn(),
  ingestionAttachments: vi.fn(),
  retryAttachment: vi.fn(),
  addPastedIngestionText: vi.fn(),
  uploadIngestionBatch: vi.fn(),
  previewOcr: vi.fn(),
  addPastedAttachment: vi.fn(),
  addFileAttachment: vi.fn(),
}))

vi.mock('../api/client', () => ({ api: apiMock, ApiClientError: class ApiClientError extends Error { status = 500; code = 'test' } }))
vi.mock('../stores/workspace', () => ({ useWorkspaceStore: () => (globalThis as any).__novelforgeWorkspace }))

describe('资料导入状态切换', () => {
  afterEach(() => {
    vi.clearAllMocks()
    delete (globalThis as any).__novelforgeWorkspace
  })

  it('旧项目请求晚于切换返回时，不会覆盖新项目资料状态', async () => {
    const workspace = reactive({ activeProjectId: 'project-old', activeStory: { story_id: 'story-old' } })
    ;(globalThis as any).__novelforgeWorkspace = workspace
    const oldWorkbench = deferred<Record<string, any>>()
    const oldAttachments = deferred<{ attachments: any[] }>()
    const newWorkbench = deferred<Record<string, any>>()
    const newAttachments = deferred<{ attachments: any[] }>()
    apiMock.ingestionWorkbench.mockImplementation((projectId: string) => projectId === 'project-old' ? oldWorkbench.promise : newWorkbench.promise)
    apiMock.ingestionAttachments.mockImplementation((projectId: string) => projectId === 'project-old' ? oldAttachments.promise : newAttachments.promise)

    const wrapper = mount(ResearchView)
    await nextTick()
    workspace.activeProjectId = 'project-new'
    workspace.activeStory = { story_id: 'story-new' }
    await nextTick()
    newWorkbench.resolve({ batch_rows: [], active_task_count: 0, failed_task_count: 0 })
    newAttachments.resolve({ attachments: [{ attachment_id: 'new-attachment', title: '新项目资料', status: 'completed' }] })
    await vi.waitFor(() => expect(wrapper.text()).toContain('新项目资料'))
    oldWorkbench.resolve({ batch_rows: [], active_task_count: 0, failed_task_count: 0 })
    oldAttachments.resolve({ attachments: [{ attachment_id: 'old-attachment', title: '旧项目资料', status: 'completed' }] })
    await Promise.resolve()
    await nextTick()
    expect(wrapper.text()).toContain('新项目资料')
    expect(wrapper.text()).not.toContain('旧项目资料')
    wrapper.unmount()
  })
})
