import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useWorkspaceStore } from './workspace'

const apiMock = vi.hoisted(() => ({
  bootstrap: vi.fn(),
  stories: vi.fn(),
  branches: vi.fn(),
  updateBranch: vi.fn(),
  createProject: vi.fn(),
  createStory: vi.fn(),
  renameStory: vi.fn(),
  setStoryMode: vi.fn(),
}))
const memoryStorage = (() => {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value) },
    removeItem: (key: string) => { values.delete(key) },
    clear: () => { values.clear() },
  }
})()
vi.mock('../api/client', () => ({
  api: apiMock,
  ApiClientError: class ApiClientError extends Error { status = 500; code = 'test' },
}))

describe('workspace branch selection', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('localStorage', memoryStorage)
    localStorage.clear()
    vi.clearAllMocks()
    apiMock.bootstrap.mockResolvedValue({ projects: [{ project_id: 'p1', name: '项目', title: '项目' }] })
    apiMock.stories.mockResolvedValue({ stories: [{ story_id: 's1', name: '故事', status: 'active', creation_mode: 'conversational' }] })
  })

  it('falls back from an archived persisted branch to the active main line', async () => {
    localStorage.setItem('novelforge.branch.p1.s1', 'branch-old')
    apiMock.branches.mockResolvedValue({ branches: [
      { branch_id: 'branch-old', story_id: 's1', name: '旧线', status: 'archived', parent_branch_id: 'branch-main' },
      { branch_id: 'branch-main', story_id: 's1', name: '主线', status: 'active', is_default: true },
    ] })
    const store = useWorkspaceStore()
    await store.load()
    expect(store.activeBranchId).toBe('branch-main')
    expect(store.activeBranch?.name).toBe('主线')
    expect(localStorage.getItem('novelforge.branch.p1.s1')).toBe('branch-main')
  })

  it('creates 项目1 and 故事1 when the local workspace is empty', async () => {
    apiMock.bootstrap
      .mockResolvedValueOnce({ projects: [] })
      .mockResolvedValueOnce({ projects: [{ project_id: 'p1', name: '项目1', title: '项目1' }] })
    apiMock.createProject.mockResolvedValue({ project: { project_id: 'p1', name: '项目1', title: '项目1' } })
    apiMock.stories
      .mockResolvedValueOnce({ stories: [{ story_id: 'default', name: '默认故事', status: 'active', creation_mode: 'planned' }] })
      .mockResolvedValueOnce({ stories: [{ story_id: 'default', name: '故事1', status: 'active', creation_mode: 'conversational' }] })
    apiMock.renameStory.mockResolvedValue({ story: { story_id: 'default', name: '故事1' } })
    apiMock.setStoryMode.mockResolvedValue({ story: { story_id: 'default', name: '故事1', creation_mode: 'conversational' } })
    apiMock.branches.mockResolvedValue({ branches: [{ branch_id: 'branch-main', story_id: 'default', name: '主线', status: 'active', is_default: true }] })

    const store = useWorkspaceStore()
    await store.load()
    await store.ensureDefaultWorkspace('conversational')

    expect(apiMock.createProject).toHaveBeenCalledWith({ name: '项目1', title: '项目1' })
    expect(apiMock.renameStory).toHaveBeenCalledWith('p1', 'default', '故事1')
    expect(apiMock.setStoryMode).toHaveBeenCalledWith('p1', 'default', 'conversational')
    expect(store.activeProject?.title).toBe('项目1')
    expect(store.activeStory?.name).toBe('故事1')
  })

  it('returns to an active sibling after archiving the current branch', async () => {
    apiMock.branches
      .mockResolvedValueOnce({ branches: [
        { branch_id: 'branch-main', story_id: 's1', name: '主线', status: 'active', is_default: true },
        { branch_id: 'branch-child', story_id: 's1', name: '获救线', status: 'active', parent_branch_id: 'branch-main' },
      ] })
      .mockResolvedValueOnce({ branches: [
        { branch_id: 'branch-main', story_id: 's1', name: '主线', status: 'active', is_default: true },
        { branch_id: 'branch-child', story_id: 's1', name: '获救线', status: 'archived', parent_branch_id: 'branch-main' },
      ] })
    apiMock.updateBranch.mockResolvedValue({ branch: { branch_id: 'branch-child', status: 'archived' } })
    const store = useWorkspaceStore()
    await store.load()
    await store.selectBranch('branch-child')
    await store.updateBranch('branch-child', { status: 'archived' })
    expect(store.activeBranchId).toBe('branch-main')
    expect(store.activeBranch?.status).toBe('active')
  })

  it('keeps separate branch choices for equal story IDs in different projects', async () => {
    apiMock.branches.mockImplementation(async (projectId: string) => ({ branches: [
      { branch_id: 'branch-main', story_id: 's1', name: '主线', status: 'active', is_default: true },
      ...(projectId === 'p1' ? [{ branch_id: 'branch-child', story_id: 's1', name: '子线', status: 'active', parent_branch_id: 'branch-main' }] : []),
    ] }))
    const store = useWorkspaceStore()
    await store.load()
    await store.selectBranch('branch-child')
    await store.selectProject('p2')
    expect(store.activeBranchId).toBe('branch-main')
    await store.selectProject('p1')
    expect(store.activeBranchId).toBe('branch-child')
  })
})
