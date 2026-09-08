<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore } from '../../stores/workspace'
import { api, ApiClientError } from '../../api/client'
import { dialog } from '../../ui/dialog'
import { notify } from '../../ui/notifications'
import NewStoryInline from '../../components/NewStoryInline.vue'
import ContextTag from '../../components/ContextTag.vue'
import { suggestSequelName } from '../../ui/naming'

const workspace = useWorkspaceStore()
const router = useRouter()
const idea = ref('')
const creating = ref(false)
const error = ref('')

const projectLabel = computed(() => workspace.activeProject?.title || workspace.activeProject?.name || '未选项目')
const storyLabel = computed(() => workspace.activeStory?.name || '')
const projectItems = computed(() =>
  workspace.projects.map((project) => ({
    value: project.project_id,
    label: project.title || project.name,
  })),
)
const storyItems = computed(() =>
  workspace.activeStories.map((story) => ({
    value: story.story_id,
    label: story.name,
  })),
)
const modePill = computed(() => (workspace.activeStory?.creation_mode === 'conversational' ? '对话故事' : '规划故事'))

async function begin() {
  if (!workspace.activeProjectId || !workspace.activeStory || !idea.value.trim()) return
  creating.value = true
  error.value = ''
  try {
    const data = await api.createSession(workspace.activeProjectId, workspace.activeStory.story_id, { session_goal: idea.value.trim(), branch_id: workspace.activeBranchId || undefined })
    await router.push({ name: 'conversational-session', params: { sessionId: data.session.session_id } })
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '会话创建失败'
  } finally {
    creating.value = false
  }
}

async function selectProjectFromTag(value: string) {
  if (!value || value === workspace.activeProjectId) return
  await workspace.selectProject(value)
}

async function selectStoryFromTag(value: string) {
  if (!value || value === workspace.activeStoryId) return
  await workspace.selectStory(value)
}

async function createProjectFromTag() {
  const suggestion = suggestSequelName('项目', workspace.projects.map((project) => project.title || project.name))
  const name = await dialog.prompt({ title: '新建项目', confirmLabel: '创建', input: { label: '项目名称', initialValue: suggestion } })
  if (!name?.trim()) return
  try {
    await workspace.createProjectAndSelect(name.trim())
    notify('项目已创建，可在此创建第一个故事', 'success')
  } catch (reason) {
    notify(reason instanceof Error ? reason.message : '项目创建失败', 'error')
  }
}

async function createStoryFromTag() {
  if (!workspace.activeProjectId) return
  const suggestion = suggestSequelName('故事', workspace.stories.map((story) => story.name))
  const name = await dialog.prompt({ title: '新建故事', confirmLabel: '创建', input: { label: '故事名称', initialValue: suggestion } })
  if (!name?.trim()) return
  try {
    const data = await api.createStory(workspace.activeProjectId, { name: name.trim(), creation_mode: 'conversational' })
    await workspace.loadStories()
    await workspace.selectStory(data.story.story_id)
    notify('故事已创建', 'success')
  } catch (reason) {
    notify(reason instanceof Error ? reason.message : '故事创建失败', 'error')
  }
}

async function renameCurrentStory() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  const next = await dialog.prompt({
    title: '重命名故事',
    confirmLabel: '保存',
    input: { label: '故事名称', initialValue: workspace.activeStory.name },
  })
  if (!next?.trim() || next.trim() === workspace.activeStory.name) return
  try {
    await api.renameStory(workspace.activeProjectId, workspace.activeStory.story_id, next.trim())
    await workspace.loadStories()
    notify('故事名称已更新', 'success')
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '故事重命名失败'
  }
}
</script>

<template>
  <section class="conversation-home"><div class="welcome"><p class="eyebrow">{{ workspace.activeStory ? '新建会话' : '开始创作' }}</p><h1 v-if="workspace.activeStory">这次要讨论或<em>写什么？</em></h1><h1 v-else>先创建一个<em>新故事</em></h1><p>{{ workspace.activeStory ? '输入一个写作目标、待解决的问题，或直接贴入要续写和修改的内容。' : '对话工作台围绕“故事”展开。为当前项目新建一个故事后，就能开始写作或讨论。' }}</p></div><div v-if="workspace.activeStory" class="composer-card unified"><div class="composer-context-row"><ContextTag label="项目" :current-label="projectLabel" :items="projectItems" create-label="新建项目" @select="selectProjectFromTag" @create="createProjectFromTag" /><i class="composer-context-divider" aria-hidden="true">▸</i><ContextTag label="故事" :current-label="storyLabel" :items="storyItems" create-label="新建故事" @select="selectStoryFromTag" @create="createStoryFromTag" /><button class="composer-rename" title="重命名当前故事" aria-label="重命名当前故事" @click="renameCurrentStory">✎</button><small class="composer-mode">{{ modePill }}</small></div><textarea v-model="idea" rows="4" aria-label="会话目标" placeholder="例如：试写主角多年后回到故乡的开场场景" @keydown.meta.enter.prevent="begin" @keydown.ctrl.enter.prevent="begin"></textarea><div class="composer-footer"><span>⌘ / Ctrl + Enter 创建会话</span><button class="button accent" :disabled="creating || !idea.trim()" @click="begin">{{ creating ? '正在创建…' : '创建会话  →' }}</button></div></div><div v-else class="composer-card new-story-card"><NewStoryInline :default-mode="'conversational'" /></div><p v-if="error" class="error">{{ error }}</p><div class="promise-row"><div><span>✦</span><strong>直接开始</strong><small>先创建会话，再按需调整设置</small></div><div><span>⌁</span><strong>保存版本</strong><small>写作片段和采用状态可追溯</small></div><div><span>◌</span><strong>保留上下文</strong><small>附件与确认知识可继续使用</small></div></div></section>
</template>

<style scoped>
.conversation-home { max-width: 780px; margin: clamp(40px, 10vh, 105px) auto 0; padding: 0 26px 70px; }
.welcome h1 { margin: 10px 0 21px; color: #f0ebe4; font-family: Georgia, serif; font-size: clamp(42px, 6.5vw, 72px); font-weight: 400; letter-spacing: -.06em; line-height: 1.05; }
.welcome h1 em { color: #e0a17d; font-style: normal; }
.welcome > p:not(.eyebrow) { max-width: 500px; margin: 0; color: #9a9e96; font-size: 14px; line-height: 1.8; }
.composer-card { margin-top: 32px; padding: 16px; border: 1px solid rgba(255,255,255,.14); border-radius: 18px; background: rgba(55,58,55,.72); box-shadow: 0 20px 55px rgba(0,0,0,.12); }
.composer-card.unified { margin-top: 26px; padding: 12px 14px 14px; }
.composer-context-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 2px 2px 8px; border-bottom: 1px solid rgba(255,255,255,.07); }
.composer-context-row :deep(.ctx-tag) { max-width: 100%; }
.composer-context-divider { color: #6f756d; font-style: normal; font-size: 11px; }
.composer-rename { padding: 2px 6px; border: 0; border-radius: 6px; color: #7f857c; background: transparent; cursor: pointer; font-size: 12px; line-height: 1; }
.composer-rename:hover { color: #f0d8c4; background: rgba(255,255,255,.07); }
.composer-mode { padding: 2px 8px; border: 1px solid rgba(255,255,255,.12); border-radius: 99px; color: #a4a99f; font-size: 10px; margin-left: auto; }
.composer-card textarea { display: block; width: 100%; resize: vertical; border: 0; outline: 0; color: #eee9e1; background: transparent; font-family: Georgia, serif; font-size: 18px; line-height: 1.7; }
.composer-card.unified textarea { margin-top: 8px; }
.composer-card textarea::placeholder { color: #a4a99f; }
.composer-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,.09); }
.composer-footer span { color: #a4a99f; font-size: 11px; }
.button:disabled { cursor: not-allowed; opacity: .45; }
.error { color: #df9e86; font-size: 13px; }
.new-story-card { min-width: 0; }
.promise-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-top: 64px; padding-top: 25px; border-top: 1px solid rgba(255,255,255,.09); }
.promise-row div { display: grid; grid-template-columns: 23px 1fr; align-items: baseline; column-gap: 7px; }
.promise-row span { color: #db9775; }
.promise-row strong { color: #cbc6bc; font-family: Georgia, serif; font-size: 14px; font-weight: 400; }
.promise-row small { grid-column: 2; margin-top: 5px; color: #a4a99f; font-size: 11px; }
@media (max-width: 650px) { .conversation-home { padding: 0 18px 45px; }.composer-footer { align-items: flex-start; flex-direction: column; gap: 13px; }.promise-row { grid-template-columns: 1fr; gap: 16px; }.composer-mode { margin-left: 0; } }
</style>
