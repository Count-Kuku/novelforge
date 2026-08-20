<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useWorkspaceStore } from '../stores/workspace'
import { api } from '../api/client'
import type { CreativeSession } from '../types'
import { dialog } from '../ui/dialog'
import { notify } from '../ui/notifications'

const workspace = useWorkspaceStore()
const router = useRouter()
const projectLabel = computed(() => workspace.activeProject?.title || workspace.activeProject?.name || '未选择项目')
const sessions = ref<CreativeSession[]>([])
const sessionError = ref('')

async function loadSessions() {
  sessionError.value = ''
  if (!workspace.activeProjectId || !workspace.activeStory) {
    sessions.value = []
    return
  }
  try {
    sessions.value = (await api.sessions(workspace.activeProjectId, workspace.activeStory.story_id)).sessions
  } catch (reason) {
    sessions.value = []
    sessionError.value = reason instanceof Error ? reason.message : '会话列表读取失败'
  }
}

onMounted(loadSessions)
watch(() => [workspace.activeProjectId, workspace.activeStoryId], loadSessions)

async function switchToPlan() {
  await workspace.setMode('planned')
  await router.push('/planned')
}

async function changeProject(event: Event) {
  await workspace.selectProject((event.target as HTMLSelectElement).value)
}

async function changeStory(event: Event) {
  await workspace.selectStory((event.target as HTMLSelectElement).value)
}

async function archiveSession(session: CreativeSession) {
  if (!workspace.activeProjectId || !workspace.activeStory || session.status === 'archived') return
  if (!await dialog.confirm({ title: '归档会话？', message: `“${session.title || session.session_goal}”将从最近会话中移除，历史内容仍会保留。`, confirmLabel: '归档会话' })) return
  try {
    await api.archiveSession(workspace.activeProjectId, workspace.activeStory.story_id, session.session_id)
    await loadSessions()
    notify('会话已归档', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '会话归档失败', 'error') }
}

async function archiveStory() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  if (!await dialog.confirm({ title: '归档当前故事？', message: `“${workspace.activeStory.name}”将从当前故事列表中移除，数据仍保留在本地数据库中。`, confirmLabel: '归档故事', tone: 'danger' })) return
  try {
    await api.archiveStory(workspace.activeProjectId, workspace.activeStory.story_id)
    await workspace.loadStories()
    notify('故事已归档', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '故事归档失败', 'error') }
}

async function deleteProject() {
  if (!workspace.activeProjectId || !workspace.activeProject) return
  const confirmation = await dialog.prompt({ title: '删除项目？', message: '此操作会移除项目数据库和本地资产，无法在界面中撤销。', confirmLabel: '删除项目', tone: 'danger', input: { label: '输入项目名称确认', match: workspace.activeProject.name } })
  if (confirmation !== workspace.activeProject.name) return
  try {
    await api.deleteProject(workspace.activeProjectId)
    localStorage.removeItem('novelforge.project')
    localStorage.removeItem('novelforge.story')
    await workspace.load()
    await router.push('/')
    notify('项目已删除', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '项目删除失败', 'error') }
}

function sessionStatusLabel(status: string) {
  return ({ active: '进行中', archived: '已归档', completed: '已完成' } as Record<string, string>)[status] || status
}
</script>

<template>
  <div class="chat-shell">
    <aside class="chat-sidebar">
      <div class="chat-brand"><div class="orb"></div><div><strong>NovelForge</strong><small>对话工作台</small></div></div>
      <div class="chat-context"><span class="context-label">当前故事</span><select class="chat-story-select" :value="workspace.activeStoryId" aria-label="选择故事" @change="changeStory"><option v-for="story in workspace.stories" :key="story.story_id" :value="story.story_id">{{ story.name }}</option></select><label class="chat-project-select"><span>{{ projectLabel }}</span><select :value="workspace.activeProjectId" aria-label="选择项目" @change="changeProject"><option v-for="project in workspace.projects" :key="project.project_id" :value="project.project_id">{{ project.title || project.name }}</option></select></label></div>
      <RouterLink class="new-chat" to="/conversational"><span>＋</span>新建创作会话</RouterLink>
      <div class="session-list"><p class="eyebrow">最近会话</p><div v-if="sessionError" class="session-empty error">{{ sessionError }}</div><template v-else><div v-for="session in sessions" :key="session.session_id" class="session-row"><RouterLink class="session-link" :to="{ name: 'conversational-session', params: { sessionId: session.session_id } }">{{ session.title || session.session_goal }}<small>{{ sessionStatusLabel(session.status) }}</small></RouterLink><button v-if="session.status !== 'archived'" class="session-archive" aria-label="归档会话" title="归档会话" @click="archiveSession(session)">···</button></div><div v-if="!sessions.length" class="session-empty">暂无会话。<br />点击上方按钮开始一次写作或讨论。</div></template></div>
      <div class="chat-sidebar-footer"><RouterLink to="/conversational/workspace"><span>⌂</span>共享工作区</RouterLink><RouterLink to="/conversational/workspace/content"><span>▦</span>内容浏览</RouterLink><RouterLink to="/conversational/workspace/entities"><span>◎</span>实体与时间线</RouterLink><RouterLink to="/conversational/workspace/graph"><span>◇</span>关系图</RouterLink><RouterLink to="/conversational/workspace/research"><span>⌁</span>网络研究</RouterLink><RouterLink to="/conversational/settings"><span>⚙</span>模型与能力</RouterLink><RouterLink to="/conversational/rules"><span>≡</span>规则与偏好</RouterLink><RouterLink to="/"><span>⇄</span>切换到规划工作台</RouterLink><button class="chat-danger" @click="archiveStory"><span>□</span>归档当前故事</button><button class="chat-danger" @click="deleteProject"><span>×</span>删除项目</button></div>
    </aside>
    <main class="chat-main"><header class="chat-topbar"><div class="mode-badge"><i></i>自由对话</div><div class="chat-top-actions"><button class="mode-toggle" @click="switchToPlan">切到规划工作台</button><span class="live-dot"></span>本地工作区 <span class="chat-avatar" aria-hidden="true">NF</span></div></header><RouterView /></main>
  </div>
</template>

<style scoped>
.chat-shell { display: grid; grid-template-columns: 302px 1fr; min-height: 100vh; color: #e8e3dc; background: #252625; }.chat-sidebar { display: flex; flex-direction: column; gap: 24px; padding: 28px 22px 20px; border-right: 1px solid rgba(255,255,255,.08); background: #202120; }.chat-brand { display: flex; align-items: center; gap: 11px; }.chat-brand strong { display: block; color: #f0ece5; font-family: Georgia, serif; font-size: 17px; }.chat-brand small { display: block; margin-top: 3px; color: #a2a69f; font-size: 11px; }.orb { width: 33px; height: 33px; border: 6px solid #bd7659; border-right-color: #dfb795; border-radius: 50%; transform: rotate(-32deg); }.chat-context { display: grid; gap: 5px; padding: 18px; border: 1px solid rgba(255,255,255,.08); border-radius: 16px; background: #292b29; }.context-label { color: #969992; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }.chat-story-select, .chat-project-select select { width: 100%; overflow: hidden; border: 0; outline: 0; color: #f2eee7; background: transparent; font-family: Georgia, serif; font-size: 17px; text-overflow: ellipsis; white-space: nowrap; }.chat-story-select option, .chat-project-select option { color: #292b2a; }.chat-project-select { display: flex; align-items: center; gap: 5px; color: #a6aaa3; font-size: 12px; }.chat-project-select select { flex: 1; color: #a6aaa3; font-family: inherit; font-size: 12px; }.new-chat { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px; border: 1px solid rgba(222,172,139,.45); border-radius: 11px; color: #e8c5ae; background: rgba(190,111,78,.12); font-size: 13px; }.new-chat span { font-size: 18px; }.session-list { min-height: 120px; }.session-list .eyebrow { color: #a6aaa3; }.session-link { display: flex; flex-direction: column; gap: 4px; padding: 9px 8px; border-radius: 9px; color: #c9c6bc; font-size: 12px; }.session-link:hover { background: rgba(255,255,255,.06); }.session-link small { color: #959b93; font-size: 10px; }.session-empty { padding: 12px 4px; color: #a2a69f; font-size: 12px; line-height: 1.8; }.chat-sidebar-footer { display: grid; gap: 10px; margin-top: auto; padding-top: 17px; border-top: 1px solid rgba(255,255,255,.08); }.chat-sidebar-footer a { display: flex; justify-content: space-between; color: #a2a69f; font-size: 12px; }.chat-sidebar-footer a span:first-child { margin-right: 7px; }.chat-main { min-width: 0; background: radial-gradient(circle at 62% 0, rgba(148,119,94,.13), transparent 36%), #292b2a; }.chat-topbar { display: flex; align-items: center; justify-content: space-between; padding: 22px clamp(22px, 5vw, 70px); border-bottom: 1px solid rgba(255,255,255,.07); }.mode-badge { display: flex; align-items: center; gap: 8px; color: #d8c8b7; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }.mode-badge i, .live-dot { width: 7px; height: 7px; border-radius: 50%; background: #d38361; box-shadow: 0 0 0 4px rgba(211,131,97,.12); }.chat-top-actions { display: flex; align-items: center; gap: 12px; color: #a2a69f; font-size: 12px; }.live-dot { width: 5px; height: 5px; background: #8baa74; box-shadow: none; }.chat-avatar { display: grid; place-items: center; width: 34px; height: 34px; border: 1px solid rgba(255,255,255,.14); border-radius: 50%; color: #d9d2c9; background: #363936; font-size: 10px; }.mode-toggle { border: 0; color: #c7987e; background: transparent; font-size: 12px; }.mode-toggle:hover { color: #e3bda2; text-decoration: underline; }
@media (max-width: 760px) { .chat-shell { grid-template-columns: 1fr; }.chat-sidebar { gap: 12px; padding: 16px; }.chat-context, .session-list { display: none; }.chat-sidebar-footer { display: none; }.chat-topbar { padding: 17px 18px; } }
</style>

<style scoped>
.session-row { display: flex; align-items: center; gap: 2px; }
.session-row .session-link { flex: 1; min-width: 0; }
.session-archive { width: 26px; height: 26px; border: 0; border-radius: 6px; color: #72776f; background: transparent; cursor: pointer; }
.session-archive:hover { color: #e0b199; background: rgba(255,255,255,.07); }
.session-empty.error { color: #d6937b; }
.chat-danger { display: flex; justify-content: space-between; padding: 0; border: 0; color: #92968e; background: transparent; cursor: pointer; font: inherit; font-size: 12px; text-align: left; }.chat-danger:hover { color: #dda18b; }.chat-danger span { margin-right: 7px; }
</style>
