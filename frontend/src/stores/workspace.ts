import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, ApiClientError } from '../api/client'
import type { CreationMode, ProjectItem, StoryItem } from '../types'

export const useWorkspaceStore = defineStore('workspace', () => {
  const projects = ref<ProjectItem[]>([])
  const activeProjectId = ref<string>(localStorage.getItem('novelforge.project') || '')
  const activeStoryId = ref<string>(localStorage.getItem('novelforge.story') || 'default')
  const stories = ref<StoryItem[]>([])
  const ready = ref(false)
  const loading = ref(false)
  const error = ref('')
  let loadTask: Promise<void> | null = null
  let storiesRequest = 0

  const activeProject = computed(() => projects.value.find((project) => project.project_id === activeProjectId.value) || null)
  const activeStories = computed(() => stories.value.filter((story) => story.status !== 'archived'))
  const archivedStories = computed(() => stories.value.filter((story) => story.status === 'archived'))
  const activeStory = computed(() => activeStories.value.find((story) => story.story_id === activeStoryId.value) || activeStories.value[0] || null)
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
  }

  async function selectProject(projectId: string) {
    if (!projectId || projectId === activeProjectId.value) return
    const request = ++storiesRequest
    const data = await api.stories(projectId)
    if (request !== storiesRequest) return
    activeProjectId.value = projectId
    applyStories(projectId, data.stories)
  }

  async function selectStory(storyId: string) {
    if (!activeStories.value.some((story) => story.story_id === storyId)) return
    activeStoryId.value = storyId
    localStorage.setItem('novelforge.story', storyId)
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
    mode,
    load,
    loadStories,
    selectProject,
    selectStory,
    setMode,
    createProjectAndSelect,
    renameActiveProject,
  }
})
