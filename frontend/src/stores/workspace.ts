import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, ApiClientError } from '../api/client'
import type { CreationMode, ProjectItem, StoryBranch, StoryItem } from '../types'

export const useWorkspaceStore = defineStore('workspace', () => {
  const projects = ref<ProjectItem[]>([])
  const activeProjectId = ref<string>(localStorage.getItem('novelforge.project') || '')
  const activeStoryId = ref<string>(localStorage.getItem('novelforge.story') || 'default')
  const stories = ref<StoryItem[]>([])
  const branches = ref<StoryBranch[]>([])
  const activeBranchId = ref<string>(localStorage.getItem('novelforge.branch') || '')
  const branchesLoading = ref(false)
  const branchesError = ref('')
  const ready = ref(false)
  const loading = ref(false)
  const error = ref('')
  let loadTask: Promise<void> | null = null
  let storiesRequest = 0
  let branchesRequest = 0

  const activeProject = computed(() => projects.value.find((project) => project.project_id === activeProjectId.value) || null)
  const activeStories = computed(() => stories.value.filter((story) => story.status !== 'archived'))
  const archivedStories = computed(() => stories.value.filter((story) => story.status === 'archived'))
  const activeStory = computed(() => activeStories.value.find((story) => story.story_id === activeStoryId.value) || activeStories.value[0] || null)
  const activeBranches = computed(() => branches.value.filter((branch) => branch.status !== 'archived'))
  const archivedBranches = computed(() => branches.value.filter((branch) => branch.status === 'archived'))
  const activeBranch = computed(() => activeBranches.value.find((branch) => branch.branch_id === activeBranchId.value) || activeBranches.value.find((branch) => branch.is_default || !branch.parent_branch_id) || activeBranches.value[0] || null)
  const mode = computed<CreationMode>(() => activeStory.value?.creation_mode || 'planned')

  async function load() {
    if (loadTask) return loadTask
    loadTask = (async () => {
    loading.value = true
    error.value = ''
    try {
      const data = await api.bootstrap()
      projects.value = data.projects
      if (!activeProjectId.value || !projects.value.some((project) => project.project_id === activeProjectId.value)) {
        activeProjectId.value = projects.value[0]?.project_id || ''
      }
      if (activeProjectId.value) await loadStories()
      ready.value = true
    } catch (reason) {
      ready.value = true
      error.value = reason instanceof ApiClientError ? reason.message : '无法连接到 NovelForge API'
    } finally {
      loading.value = false
    }
    })()
    try {
      await loadTask
    } finally {
      loadTask = null
    }
  }

  function applyStories(projectId: string, nextStories: StoryItem[]) {
    if (projectId !== activeProjectId.value) return
    stories.value = nextStories
    if (!activeStories.value.some((story) => story.story_id === activeStoryId.value)) {
      activeStoryId.value = activeStories.value[0]?.story_id || ''
    }
    localStorage.setItem('novelforge.project', activeProjectId.value)
    if (activeStoryId.value) localStorage.setItem('novelforge.story', activeStoryId.value)
    else localStorage.removeItem('novelforge.story')
  }

  async function loadStories() {
    const projectId = activeProjectId.value
    if (!projectId) {
      stories.value = []
      return
    }
    const request = ++storiesRequest
    const data = await api.stories(projectId)
    if (request !== storiesRequest || projectId !== activeProjectId.value) return
    applyStories(projectId, data.stories)
    await loadBranches()
  }

  async function selectProject(projectId: string) {
    if (!projectId || projectId === activeProjectId.value) return
    const request = ++storiesRequest
    const data = await api.stories(projectId)
    if (request !== storiesRequest) return
    activeProjectId.value = projectId
    applyStories(projectId, data.stories)
    await loadBranches()
  }

  async function selectStory(storyId: string) {
    if (!activeStories.value.some((story) => story.story_id === storyId)) return
    activeStoryId.value = storyId
    localStorage.setItem('novelforge.story', storyId)
    await loadBranches()
  }

  async function loadBranches(includeArchived = true) {
    const projectId = activeProjectId.value
    const storyId = activeStoryId.value
    const request = ++branchesRequest
    if (!projectId || !storyId) {
      branches.value = []
      activeBranchId.value = ''
      return
    }
    branchesLoading.value = true
    branchesError.value = ''
    try {
      const data = await api.branches(projectId, storyId, includeArchived)
      if (request !== branchesRequest || projectId !== activeProjectId.value || storyId !== activeStoryId.value) return
      branches.value = data.branches || []
      const activeBranchRows = (data.branches || []).filter((branch) => branch.status !== 'archived')
      const persisted = localStorage.getItem(`novelforge.branch.${projectId}.${storyId}`)
      const selected = (data.active_branch_id && activeBranchRows.some((branch) => branch.branch_id === data.active_branch_id))
        ? data.active_branch_id
        : persisted && activeBranchRows.some((branch) => branch.branch_id === persisted) ? persisted : activeBranchRows.find((branch) => branch.is_default || !branch.parent_branch_id)?.branch_id || activeBranchRows[0]?.branch_id || ''
      activeBranchId.value = selected || ''
      if (selected) {
        localStorage.setItem('novelforge.branch', selected)
        localStorage.setItem(`novelforge.branch.${projectId}.${storyId}`, selected)
      } else localStorage.removeItem('novelforge.branch')
    } catch (reason) {
      if (request !== branchesRequest || projectId !== activeProjectId.value || storyId !== activeStoryId.value) return
      branches.value = []
      activeBranchId.value = ''
      localStorage.removeItem('novelforge.branch')
      branchesError.value = reason instanceof ApiClientError ? reason.message : '无法读取世界线'
      // Branch APIs are optional during legacy migration. Keep the story usable
      // and let the session surface a clear migration notice when needed.
    } finally {
      if (request === branchesRequest && projectId === activeProjectId.value && storyId === activeStoryId.value) branchesLoading.value = false
    }
  }

  async function selectBranch(branchId: string) {
    if (!activeBranches.value.some((branch) => branch.branch_id === branchId)) return
    activeBranchId.value = branchId
    localStorage.setItem('novelforge.branch', branchId)
    if (activeProjectId.value && activeStoryId.value) localStorage.setItem(`novelforge.branch.${activeProjectId.value}.${activeStoryId.value}`, branchId)
  }

  async function createBranch(payload: { name: string; description?: string; parent_branch_id?: string; fork_fragment_id?: string; fork_checkpoint_id?: string; allow_current_state?: boolean }) {
    if (!activeProjectId.value || !activeStory.value) throw new Error('请先选择故事')
    const data = await api.createBranch(activeProjectId.value, activeStory.value.story_id, payload)
    await loadBranches()
    if (data.branch?.branch_id) await selectBranch(data.branch.branch_id)
    return data.branch
  }

  async function forkBranch(payload: { name: string; description?: string; fork_fragment_id?: string; fork_checkpoint_id?: string; allow_current_state?: boolean }, parentBranchId = activeBranchId.value) {
    if (!activeProjectId.value || !activeStory.value || !parentBranchId) throw new Error('请先选择要分叉的世界线')
    const data = await api.forkBranch(activeProjectId.value, activeStory.value.story_id, parentBranchId, payload)
    await loadBranches()
    if (data.branch?.branch_id) await selectBranch(data.branch.branch_id)
    return data
  }

  async function updateBranch(branchId: string, patch: { name?: string; description?: string; status?: 'active' | 'archived' }) {
    if (!activeProjectId.value || !activeStory.value) throw new Error('请先选择故事')
    const data = await api.updateBranch(activeProjectId.value, activeStory.value.story_id, branchId, patch)
    await loadBranches()
    return data.branch
  }

  async function setMode(nextMode: CreationMode) {
    if (!activeProjectId.value || !activeStory.value) return
    const data = await api.setStoryMode(activeProjectId.value, activeStory.value.story_id, nextMode)
    const index = stories.value.findIndex((story) => story.story_id === data.story.story_id)
    if (index >= 0) stories.value[index] = data.story
  }

  async function createProjectAndSelect(name: string) {
    const data = await api.createProject({ name, title: name })
    const projectId = data.project.project_id
    await load()
    await selectProject(projectId)
    return data.project
  }

  async function renameActiveProject(nextName: string) {
    if (!activeProjectId.value) return
    const data = await api.renameProject(activeProjectId.value, nextName)
    await load()
    return data.project
  }

  return {
    projects,
    activeProjectId,
    activeStoryId,
    stories,
    ready,
    loading,
    error,
    activeProject,
    activeStories,
    archivedStories,
    activeStory,
    branches,
    activeBranches,
    archivedBranches,
    activeBranchId,
    activeBranch,
    branchesLoading,
    branchesError,
    mode,
    load,
    loadStories,
    selectProject,
    selectStory,
    loadBranches,
    selectBranch,
    createBranch,
    forkBranch,
    updateBranch,
    setMode,
    createProjectAndSelect,
    renameActiveProject,
  }
})
