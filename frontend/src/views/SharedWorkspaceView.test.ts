import { nextTick, reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SharedWorkspaceView from './SharedWorkspaceView.vue'

const deferred = <T>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => { resolve = res })
  return { promise, resolve }
}

const apiMock = vi.hoisted(() => ({
  summary: vi.fn(),
  tasks: vi.fn(),
  capabilities: vi.fn(),
  pendingKnowledge: vi.fn(),
  developerSettings: vi.fn(),
  searchKnowledge: vi.fn(),
  resolvePendingEntity: vi.fn(),
}))

vi.mock('../api/client', () => ({ api: apiMock, ApiClientError: class ApiClientError extends Error { status = 500; code = 'test' } }))
vi.mock('../stores/workspace', () => ({ useWorkspaceStore: () => (globalThis as any).__novelforgeWorkspace }))
vi.mock('vue-router', () => ({
  RouterLink: { template: '<a><slot /></a>' },
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn().mockResolvedValue(undefined), push: vi.fn().mockResolvedValue(undefined) }),
}))
vi.mock('../ui/notifications', () => ({ notify: vi.fn() }))

function workspaceFixture() {
  return reactive({
    activeProjectId: 'project-1',
    activeStory: { story_id: 'story-1', name: '故事', creation_mode: 'conversational' },
    activeStoryId: 'story-1',
    activeBranchId: 'branch-main',
    mode: 'conversational',
  })
}

function mountView(workspace: any) {
  ;(globalThis as any).__novelforgeWorkspace = workspace
  return mount(SharedWorkspaceView)
}

describe('知识中心当前世界线交互', () => {
  afterEach(() => {
    vi.clearAllMocks()
    delete (globalThis as any).__novelforgeWorkspace
  })

  it('旧世界线搜索响应晚到时不会覆盖新世界线结果', async () => {
    const workspace = workspaceFixture()
    const oldSearch = deferred<{ items: any[]; next_cursor?: string }>()
    apiMock.summary.mockResolvedValue({})
    apiMock.tasks.mockResolvedValue({ ingestion: [] })
    apiMock.capabilities.mockResolvedValue({ capabilities: {} })
    apiMock.pendingKnowledge.mockResolvedValue({ items: [] })
    apiMock.developerSettings.mockResolvedValue({ enabled: false })
    apiMock.searchKnowledge.mockImplementation((_: string, __: string, ___: string, cursor: string, _____: number, ______: string, branchId?: string) => branchId === 'branch-child' ? Promise.resolve({ items: [{ name: '新线结果' }], next_cursor: '' }) : cursor ? Promise.resolve({ items: [{ name: '新线结果' }], next_cursor: '' }) : oldSearch.promise)
    const wrapper = mountView(workspace)
    await flushPromises()
    await wrapper.get('input[aria-label="搜索知识"]').setValue('角色')
    await wrapper.get('button.button.accent').trigger('click')
    workspace.activeBranchId = 'branch-child'
    await nextTick()
    oldSearch.resolve({ items: [{ name: '旧线结果' }], next_cursor: '' })
    await flushPromises()
    expect(wrapper.text()).not.toContain('旧线结果')
    wrapper.unmount()
  })

  it('同名实体待确认时必须先选择来源，再允许正式确认', async () => {
    const workspace = workspaceFixture()
    let resolved = false
    const pending = {
      pending_id: 'pending-1',
      name: '林越',
      category: 'characters',
      entity_resolution_status: 'pending_confirmation',
      entity_resolution_endpoint: 'source',
      entity_resolution_options: [
        { entity_id: 'entity-a', canonical_name: '林越', worldline_id: '世界 A', aliases: [] },
        { entity_id: 'entity-b', canonical_name: '林越', worldline_id: '世界 B', aliases: [] },
      ],
    }
    apiMock.summary.mockResolvedValue({})
    apiMock.tasks.mockResolvedValue({ ingestion: [] })
    apiMock.capabilities.mockResolvedValue({ capabilities: {} })
    apiMock.pendingKnowledge.mockImplementation(() => Promise.resolve({ items: [resolved ? { ...pending, entity_resolution_status: 'resolved', entity_resolution_options: [] } : pending] }))
    apiMock.developerSettings.mockResolvedValue({ enabled: false })
    apiMock.resolvePendingEntity.mockImplementation(async () => {
      resolved = true
      return { candidate: { ...pending, entity_resolution_status: 'resolved' }, resolved: true }
    })
    const wrapper = mountView(workspace)
    await flushPromises()
    expect(wrapper.text()).toContain('关系起点的来源不唯一')
    const confirm = wrapper.get('.pending-resolution .pending-button.confirm')
    expect((confirm.element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.get('.pending-resolution select').setValue('entity-b')
    expect((confirm.element as HTMLButtonElement).disabled).toBe(false)
    await confirm.trigger('click')
    expect(apiMock.resolvePendingEntity).toHaveBeenCalledWith('project-1', 'pending-1', 'entity-b', 'story-1', 'branch-main')
    await flushPromises()
    const formalConfirm = wrapper.findAll('.pending-button.confirm').at(-1)
    expect(formalConfirm).toBeDefined()
    expect((formalConfirm!.element as HTMLButtonElement).disabled).toBe(false)
    wrapper.unmount()
  })
})
