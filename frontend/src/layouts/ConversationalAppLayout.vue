<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useWorkspaceStore } from '../stores/workspace'
import { api } from '../api/client'
import type { CreativeSession } from '../types'
import { dialog } from '../ui/dialog'
import { notify } from '../ui/notifications'
import { clearAllEditorDirty, hasDirtyEditors } from '../ui/dirty'
import { suggestSequelName } from '../ui/naming'
import { conversationRouteTarget, mostRecentActiveSession } from '../ui/sessionNavigation'
import NewStoryInline from '../components/NewStoryInline.vue'

const workspace = useWorkspaceStore()
const route = useRoute()
const router = useRouter()
const viewKey = computed(() => `${workspace.activeProjectId}:${workspace.activeStoryId}:${workspace.activeBranchId}:${route.fullPath}`)
const sessions = ref<CreativeSession[]>([])
const chatRouteTarget = computed(() => conversationRouteTarget(sessions.value))
const sessionError = ref('')
const landedStoryKey = ref('')
let sessionsRequest = 0
let landingRequest = 0

function scopeKey() {
  return workspace.activeProjectId && workspace.activeStory
    ? `${workspace.activeProjectId}:${workspace.activeStory.story_id}:${workspace.activeBranchId || ''}`
    : ''
}

function isCurrentScope(key: string) {
  return key === scopeKey()
}

function isDirectSessionRoute() {
  return route.name === 'conversational-session' && Boolean(String(route.params.sessionId || ''))
}

async function loadSessions() {
  sessionError.value = ''
  if (!workspace.activeProjectId || !workspace.activeStory) {
    sessions.value = []
    return
  }
  const request = ++sessionsRequest
  const requestedScope = scopeKey()
  const projectId = workspace.activeProjectId
  const storyId = workspace.activeStory.story_id
  const branchId = workspace.activeBranchId || undefined
  try {
    const nextSessions = (await api.sessions(projectId, storyId, branchId)).sessions
    if (request === sessionsRequest && isCurrentScope(requestedScope)) sessions.value = nextSessions
  } catch (reason) {
    if (request === sessionsRequest && isCurrentScope(requestedScope)) {
      sessions.value = []
      sessionError.value = reason instanceof Error ? reason.message : '会话列表读取失败'
    }
  }
}

function currentStoryKey() {
  return scopeKey()
}

/**
 * A bookmarked session carries its owning branch in the session response. Resolve
 * that branch before the sidebar tries to choose a recent session. This keeps a
 * direct link stable when the persisted workspace branch is stale or belongs to
 * another browser window.
 */
async function resolveDirectSessionBranch(expectedLandingRequest = landingRequest) {
  if (!isDirectSessionRoute() || !workspace.activeProjectId || !workspace.activeStory) return true
  const projectId = workspace.activeProjectId
  const storyId = workspace.activeStory.story_id
  const sessionId = String(route.params.sessionId || '')
  const requestedScope = scopeKey()
  const isTargetStillCurrent = () => (
    expectedLandingRequest === landingRequest
    && isCurrentScope(requestedScope)
    && isDirectSessionRoute()
    && String(route.params.sessionId || '') === sessionId
  )
  try {
    // Omit branch_id for this discovery read: the endpoint returns the owner
    // branch, whereas sending the persisted branch would reject before we can
    // switch to the direct link's target.
    const data = await api.session(projectId, storyId, sessionId)
    if (!isTargetStillCurrent()) return false
    const ownerBranchId = String(data.session?.branch_id || '')
    if (!ownerBranchId || ownerBranchId === String(workspace.activeBranchId || '')) return isCurrentScope(requestedScope)
    if (!workspace.activeBranches.some((branch) => String(branch.branch_id) === ownerBranchId)) {
      // Direct links can mount before the workspace's initial branch request
      // has completed. Refresh the full branch list before declaring the
      // session unavailable.
      await workspace.loadBranches(true)
    }
    if (!isTargetStillCurrent()) return false
    if (!workspace.activeBranches.some((branch) => String(branch.branch_id) === ownerBranchId)) {
      sessionError.value = '当前会话属于已归档或不可用的世界线。'
      return false
    }
    await workspace.selectBranch(ownerBranchId)
    return false
  } catch (reason) {
    if (isTargetStillCurrent()) sessionError.value = reason instanceof Error ? reason.message : '无法读取目标会话'
    return false
  }
}

async function createBlankSession() {
  if (!workspace.activeProjectId || !workspace.activeStory) return ''
  const data = await api.createSession(workspace.activeProjectId, workspace.activeStory.story_id, { session_goal: '', branch_id: workspace.activeBranchId || undefined })
  await loadSessions()
  return data.session.session_id
}

/** 落在「对话/会话」上下文时：自动进入最近会话；若无任何会话则建空白会话直达（输入框立即可发）。 */
async function landOnRecentOrNew() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  const inChatContext = route.name === 'conversational-home' || route.name === 'conversational-session'
  // A direct session URL is already the user's target. Never replace it with
  // the most recent session while its owner branch is being resolved.
  if (isDirectSessionRoute()) return
  const key = currentStoryKey()
  if (!inChatContext) {
    landedStoryKey.value = key
    return
  }
  if (key === landedStoryKey.value) return
  landedStoryKey.value = key
  try {
    const recent = mostRecentActiveSession(sessions.value)
    if (recent) {
      await router.push({ name: 'conversational-session', params: { sessionId: recent.session_id } })
    } else {
      const sessionId = await createBlankSession()
      if (sessionId) await router.push({ name: 'conversational-session', params: { sessionId } })
    }
  } catch (reason) {
    sessionError.value = reason instanceof Error ? reason.message : '无法进入最近会话'
  }
}

async function syncSessionsAndLand() {
  const request = ++landingRequest
  const requestedScope = scopeKey()
  if (isDirectSessionRoute()) {
    const resolved = await resolveDirectSessionBranch(request)
    if (!resolved || request !== landingRequest) return
  }
  await loadSessions()
  if (request !== landingRequest || !isCurrentScope(requestedScope) && !isDirectSessionRoute()) return
  await landOnRecentOrNew()
}

async function startNewChat() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  try {
    const sessionId = await createBlankSession()
    if (sessionId) await router.push({ name: 'conversational-session', params: { sessionId } })
  } catch (reason) {
    notify(reason instanceof Error ? reason.message : '会话创建失败', 'error')
  }
}

onMounted(syncSessionsAndLand)
watch(() => [workspace.activeProjectId, workspace.activeStoryId, workspace.activeBranchId], syncSessionsAndLand)

async function changeProject(event: Event) {
  const projectId = (event.target as HTMLSelectElement).value
  if (hasDirtyEditors.value && !await dialog.confirm({ title: '放弃未保存修改？', message: '切换项目会重新加载当前页面，尚未保存的修改将丢失。', confirmLabel: '继续切换', tone: 'danger' })) return
  clearAllEditorDirty()
  landingRequest += 1
  if (isDirectSessionRoute()) await router.push({ name: 'conversational-home' })
  await workspace.selectProject(projectId)
}

async function changeStory(event: Event) {
  const storyId = (event.target as HTMLSelectElement).value
  if (hasDirtyEditors.value && !await dialog.confirm({ title: '放弃未保存修改？', message: '切换故事会重新加载当前页面，尚未保存的修改将丢失。', confirmLabel: '继续切换', tone: 'danger' })) return
  clearAllEditorDirty()
  landingRequest += 1
  if (isDirectSessionRoute()) await router.push({ name: 'conversational-home' })
  await workspace.selectStory(storyId)
}

async function createProject() {
  if (hasDirtyEditors.value && !await dialog.confirm({ title: '放弃未保存修改？', message: '新建项目会重新加载当前页面，尚未保存的修改将丢失。', confirmLabel: '继续', tone: 'danger' })) return
  clearAllEditorDirty()
  const suggestion = suggestSequelName('项目', workspace.projects.map((item) => item.title || item.name))
  const name = await dialog.prompt({ title: '新建项目', confirmLabel: '创建', input: { label: '项目名称', initialValue: suggestion } })
  if (!name?.trim()) return
  try {
    await workspace.createProjectAndSelect(name.trim())
    notify('项目已创建，可在此创建第一个故事', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '项目创建失败', 'error') }
}

async function renameProject() {
  if (!workspace.activeProjectId || !workspace.activeProject) return
  const name = await dialog.prompt({ title: '重命名项目', confirmLabel: '保存', input: { label: '项目名称', initialValue: workspace.activeProject.title || workspace.activeProject.name } })
  if (!name?.trim() || name.trim() === (workspace.activeProject.title || workspace.activeProject.name)) return
  try {
    await workspace.renameActiveProject(name.trim())
    notify('项目名称已更新', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '项目重命名失败', 'error') }
}

async function createStoryInSidebar() {
  if (!workspace.activeProjectId) return
  if (hasDirtyEditors.value && !await dialog.confirm({ title: '放弃未保存修改？', message: '新建故事会切换当前页面，尚未保存的修改将丢失。', confirmLabel: '继续', tone: 'danger' })) return
  clearAllEditorDirty()
  const suggestion = suggestSequelName('故事', workspace.stories.map((item) => item.name))
  const name = await dialog.prompt({ title: '新建故事', confirmLabel: '创建', input: { label: '故事名称', initialValue: suggestion } })
  if (!name?.trim()) return
  try {
    const data = await api.createStory(workspace.activeProjectId, { name: name.trim(), creation_mode: 'conversational' })
    await workspace.loadStories()
    await workspace.selectStory(data.story.story_id)
    notify('故事已创建', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '故事创建失败', 'error') }
}

async function renameCurrentStory() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  const name = await dialog.prompt({ title: '重命名故事', confirmLabel: '保存', input: { label: '故事名称', initialValue: workspace.activeStory.name } })
  if (!name?.trim() || name.trim() === workspace.activeStory.name) return
  try {
    await api.renameStory(workspace.activeProjectId, workspace.activeStory.story_id, name.trim())
    await workspace.loadStories()
    notify('故事名称已更新', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '故事重命名失败', 'error') }
}

async function changeBranch(event: Event) {
  const branchId = (event.target as HTMLSelectElement).value
  if (hasDirtyEditors.value && !await dialog.confirm({ title: '放弃未保存修改？', message: '切换世界线会重新读取当前会话，尚未保存的修改将丢失。', confirmLabel: '继续切换', tone: 'danger' })) return
  clearAllEditorDirty()
  landingRequest += 1
  if (isDirectSessionRoute()) await router.push({ name: 'conversational-home' })
  await workspace.selectBranch(branchId)
}

async function createBranchFromSidebar() {
  if (!workspace.activeBranch) return
  const name = await dialog.prompt({ title: '创建世界线', message: '命名后会从当前世界线的最新检查点建立独立前沿。', confirmLabel: '创建', input: { label: '世界线名称', initialValue: '新的可能性' } })
  if (!name?.trim()) return
  try {
    await workspace.forkBranch({ name: name.trim() }, workspace.activeBranch.branch_id)
    notify('世界线已创建并切换', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '世界线创建失败', 'error') }
}

async function renameBranch() {
  if (!workspace.activeBranch) return
  const name = await dialog.prompt({ title: '重命名世界线', confirmLabel: '保存', input: { label: '世界线名称', initialValue: workspace.activeBranch.name } })
  if (!name?.trim() || name.trim() === workspace.activeBranch.name) return
  try { await workspace.updateBranch(workspace.activeBranch.branch_id, { name: name.trim() }); notify('世界线名称已更新', 'success') }
  catch (reason) { notify(reason instanceof Error ? reason.message : '世界线重命名失败', 'error') }
}

async function archiveBranch() {
  const branch = workspace.activeBranch
  if (!branch || branch.parent_branch_id == null) return
  if (!await dialog.confirm({ title: '归档当前世界线？', message: '归档会隐藏入口并保留正文、检查点和后代引用；仍可从设置恢复。', confirmLabel: '归档世界线' })) return
  try {
    await workspace.updateBranch(branch.branch_id, { status: 'archived' })
    const fallback = workspace.activeBranches[0]
    if (fallback) await workspace.selectBranch(fallback.branch_id)
    notify('世界线已归档', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '世界线归档失败', 'error') }
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

function sessionStatusLabel(status: string) {
  return ({ active: '进行中', archived: '已归档', completed: '已完成' } as Record<string, string>)[status] || status
}
</script>

<template>
  <div class="chat-shell">
    <aside class="chat-sidebar">
      <div class="chat-brand"><div class="orb"></div><div><strong>NovelForge</strong><small>对话工作台</small></div></div>
      <div class="chat-context"><div class="context-project"><span class="context-label">项目</span><div class="project-actions"><label class="chat-project-select"><span class="project-dot"></span><select :value="workspace.activeProjectId" aria-label="选择项目" @change="changeProject"><option v-if="!workspace.projects.length" value="">暂无项目</option><option v-for="project in workspace.projects" :key="project.project_id" :value="project.project_id">{{ project.title || project.name }}</option></select></label><button class="project-action" title="新建项目" aria-label="新建项目" @click="createProject">＋</button><button class="project-action" title="重命名当前项目" aria-label="重命名当前项目" :disabled="!workspace.activeProjectId" @click="renameProject">✎</button></div></div><div v-if="workspace.activeStories.length" class="context-story"><span class="context-label">当前故事</span><div class="story-actions"><label class="chat-story-cap"><select class="chat-story-select" :value="workspace.activeStoryId" aria-label="选择故事" @change="changeStory"><option v-for="story in workspace.activeStories" :key="story.story_id" :value="story.story_id">{{ story.name }}</option></select></label><button class="project-action" title="新建故事" aria-label="新建故事" @click="createStoryInSidebar">＋</button><button class="project-action" title="重命名当前故事" aria-label="重命名当前故事" @click="renameCurrentStory">✎</button></div></div><div v-if="workspace.activeStory && workspace.activeBranches.length" class="context-branch"><span class="context-label">世界线</span><div class="branch-actions"><label class="chat-story-cap"><select class="chat-story-select branch-select" :value="workspace.activeBranchId" aria-label="选择世界线" @change="changeBranch"><option v-for="branch in workspace.activeBranches" :key="branch.branch_id" :value="branch.branch_id">{{ branch.name }}{{ branch.parent_branch_id ? '' : ' · 主线' }}</option></select></label><button class="project-action" title="新建世界线" aria-label="新建世界线" @click="createBranchFromSidebar">＋</button><button class="project-action" title="重命名当前世界线" aria-label="重命名当前世界线" @click="renameBranch">✎</button><button v-if="workspace.activeBranch?.parent_branch_id" class="project-action" title="归档当前世界线" aria-label="归档当前世界线" @click="archiveBranch">□</button></div><small v-if="workspace.activeBranch?.fork_fragment_id" class="branch-hint">从已确认片段继承 · {{ workspace.activeBranch.fork_fragment_id.slice(-8) }}</small></div><p v-if="workspace.branchesError" class="branch-hint">世界线功能暂不可用，当前仍可使用旧故事内容。</p><NewStoryInline v-if="!workspace.activeStories.length" :default-mode="'conversational'" /></div>
      <button class="new-chat" type="button" @click="startNewChat"><span>＋</span>新建创作会话</button>
      <div class="session-list"><p class="eyebrow">最近会话</p><div v-if="sessionError" class="session-empty error">{{ sessionError }}</div><template v-else><div v-for="session in sessions" :key="session.session_id" class="session-row"><RouterLink class="session-link" :to="{ name: 'conversational-session', params: { sessionId: session.session_id } }">{{ session.title || session.session_goal }}<small>{{ sessionStatusLabel(session.status) }}</small></RouterLink><button v-if="session.status !== 'archived'" class="session-archive" aria-label="归档会话" title="归档会话" @click="archiveSession(session)">···</button></div><div v-if="!sessions.length" class="session-empty">暂无会话。<br />点击上方按钮开始一次写作或讨论。</div></template></div>
      <nav class="chat-sidebar-footer" aria-label="对话工作台主导航"><RouterLink :to="chatRouteTarget" :class="{ active: route.name === 'conversational-home' || route.name === 'conversational-session' }"><span>✦</span>对话</RouterLink><RouterLink to="/conversational/works" active-class="active"><span>▤</span>作品</RouterLink><RouterLink to="/conversational/library" active-class="active"><span>▦</span>资料库</RouterLink><RouterLink to="/conversational/settings" active-class="active"><span>⚙</span>设置</RouterLink></nav>
    </aside>
    <main class="chat-main"><header class="chat-topbar"><div class="mode-badge"><i></i>自由对话</div><div class="chat-top-actions"><span class="live-dot"></span>本地工作区 <span class="chat-avatar" aria-hidden="true">NF</span></div></header><RouterView :key="viewKey" /></main>
  </div>
</template>

<style scoped>
.chat-shell { --ink: #e8e3dc; --muted: #b3aea6; --line: rgba(255,255,255,.13); --paper: #2f312f; --paper-strong: #363936; --accent: #e0a17d; --accent-soft: rgba(224,161,125,.15); --sage: #8eaa82; display: grid; grid-template-columns: 302px 1fr; min-height: 100vh; color: #e8e3dc; color-scheme: dark; background: #252625; }.chat-sidebar { position: sticky; top: 0; display: flex; flex-direction: column; align-self: start; gap: 24px; height: 100vh; height: 100dvh; min-height: 0; overflow: hidden; padding: 28px 22px 20px; border-right: 1px solid rgba(255,255,255,.08); background: #202120; }.chat-brand, .chat-context, .new-chat { flex: 0 0 auto; }.chat-brand { display: flex; align-items: center; gap: 11px; }.chat-brand strong { display: block; color: #f0ece5; font-family: Georgia, serif; font-size: 17px; }.chat-brand small { display: block; margin-top: 3px; color: #a2a69f; font-size: 11px; }.orb { width: 33px; height: 33px; border: 6px solid #bd7659; border-right-color: #dfb795; border-radius: 50%; transform: rotate(-32deg); }.chat-context { display: grid; gap: 12px; padding: 18px; border: 1px solid rgba(255,255,255,.08); border-radius: 16px; background: #292b29; }
.chat-context .context-project, .chat-context .context-story { display: grid; gap: 5px; min-width: 0; }
.chat-context .project-actions { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 4px; align-items: center; }
.chat-context .project-actions .chat-project-select { min-width: 0; }
.chat-context .story-actions { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 4px; align-items: center; }
.chat-story-cap { display: flex; align-items: center; gap: 6px; min-width: 0; padding: 7px 10px; border: 1px solid rgba(255,255,255,.14); border-radius: 10px; color: #c9c2b6; }
.chat-story-cap:focus-within { border-color: rgba(222,172,139,.5); }
.chat-story-cap select { flex: 1; min-width: 0; border: 0; outline: 0; color: #f2eee7; background: transparent; font-family: Georgia, serif; font-size: 14px; text-overflow: ellipsis; }
.chat-story-cap select option { color: #ece7df; background: #292b2a; }
.project-action { width: 24px; height: 24px; padding: 0; border: 1px solid rgba(255,255,255,.1); border-radius: 7px; color: #a6aaa3; background: transparent; font-size: 13px; line-height: 1; }
.project-action:hover { color: #f0d8c4; border-color: rgba(222,172,139,.45); }
.project-action:disabled { cursor: not-allowed; opacity: .4; }
.chat-context .context-story { padding-top: 12px; border-top: 1px solid rgba(255,255,255,.07); }.context-label { color: #969992; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }.chat-story-select, .chat-project-select select { width: 100%; overflow: hidden; border: 0; outline: 0; color: #f2eee7; background: transparent; font-family: Georgia, serif; font-size: 17px; text-overflow: ellipsis; white-space: nowrap; }.chat-story-select option, .chat-project-select option { color: #ece7df; background: #292b2a; }.chat-story-select option:checked, .chat-project-select option:checked { color: #fff4ea; background: #6a493c; font-weight: 600; }.chat-project-select { display: flex; align-items: center; gap: 6px; min-width: 0; padding: 6px 9px; border: 1px solid rgba(255,255,255,.1); border-radius: 9px; color: #a6aaa3; }
.chat-context .context-branch { display: grid; gap: 5px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.07); }
.branch-actions { display: grid; grid-template-columns: minmax(0, 1fr) auto auto auto; gap: 4px; align-items: center; }
.branch-select { font-size: 14px; }
.branch-hint { margin: 0; color: #8f968d; font-size: 9px; line-height: 1.5; }
.chat-project-select select { flex: 1; min-width: 0; color: #a6aaa3; background: transparent; font-family: inherit; font-size: 12px; }
.project-dot { flex: 0 0 7px; width: 7px; height: 7px; border-radius: 50%; background: var(--sage); }
.chat-story-select { min-width: 0; font-size: 18px; }.new-chat { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 12px; border: 1px solid rgba(222,172,139,.45); border-radius: 11px; color: #e8c5ae; background: rgba(190,111,78,.12); font-family: inherit; font-size: 13px; cursor: pointer; }.new-chat span { font-size: 18px; }.session-list { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding-right: 4px; scrollbar-gutter: stable; }.session-list .eyebrow { color: #a6aaa3; }.session-link { display: flex; flex-direction: column; gap: 4px; padding: 9px 8px; border-radius: 9px; color: #c9c6bc; font-size: 12px; }.session-link:hover { background: rgba(255,255,255,.06); }.session-link small { color: #959b93; font-size: 10px; }.session-empty { padding: 12px 4px; color: #a2a69f; font-size: 12px; line-height: 1.8; }.chat-sidebar-footer { display: grid; flex: 0 0 auto; gap: 5px; padding-top: 13px; border-top: 1px solid rgba(255,255,255,.08); }.chat-sidebar-footer a { display: grid; grid-template-columns: 24px minmax(0,1fr); align-items: center; gap: 8px; padding: 8px 9px; border-radius: 8px; color: #a2a69f; font-size: 12px; }.chat-sidebar-footer a:hover { color: #d9d3ca; background: rgba(255,255,255,.045); }.chat-sidebar-footer a.active { color: #e7bea6; background: rgba(211,131,97,.1); }.chat-sidebar-footer a span { color: #d08b6e; text-align: center; }.chat-main { min-width: 0; background: radial-gradient(circle at 62% 0, rgba(148,119,94,.13), transparent 36%), #292b2a; }.chat-topbar { display: flex; align-items: center; justify-content: space-between; padding: 22px clamp(22px, 5vw, 70px); border-bottom: 1px solid rgba(255,255,255,.07); }.mode-badge { display: flex; align-items: center; gap: 8px; color: #d8c8b7; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }.mode-badge i, .live-dot { width: 7px; height: 7px; border-radius: 50%; background: #d38361; box-shadow: 0 0 0 4px rgba(211,131,97,.12); }.chat-top-actions { display: flex; align-items: center; gap: 12px; color: #a2a69f; font-size: 12px; }.live-dot { width: 5px; height: 5px; background: #8baa74; box-shadow: none; }.chat-avatar { display: grid; place-items: center; width: 34px; height: 34px; border: 1px solid rgba(255,255,255,.14); border-radius: 50%; color: #d9d2c9; background: #363936; font-size: 10px; }
.chat-main :deep(.button) { color: #f8f3ed; background: #4a4d49; }.chat-main :deep(.button:hover) { background: #595d58; }.chat-main :deep(.button.secondary) { color: #e8e3dc; background: #3a3d3a; box-shadow: inset 0 0 0 1px rgba(255,255,255,.11); }.chat-main :deep(.button.secondary:hover) { background: #454945; }.chat-main :deep(.button.accent) { color: #fffaf4; background: #a94b2f; }.chat-main :deep(.button.accent:hover) { background: #8f3f2a; }
.chat-main :deep(select) { border-color: rgba(255,255,255,.14); color: #ece7df; color-scheme: dark; background-color: #343735; }.chat-main :deep(select:focus-visible) { border-color: rgba(224,161,125,.6); outline: 3px solid rgba(224,161,125,.16); outline-offset: 1px; }.chat-main :deep(select option) { color: #ece7df; background: #292b2a; }.chat-main :deep(select option:checked) { color: #fff4ea; background: #6a493c; font-weight: 600; }
@media (max-height: 720px) and (min-width: 761px) { .chat-sidebar { gap: 16px; padding-top: 20px; padding-bottom: 14px; }.chat-context { padding: 14px; }.chat-sidebar-footer { gap: 7px; padding-top: 12px; }.session-link { padding-block: 6px; } }
@media (max-width: 760px) { .chat-shell { grid-template-columns: 1fr; }.chat-sidebar { position: static; height: auto; overflow: visible; gap: 12px; padding: 16px; }.chat-context, .session-list { display: none; }.chat-sidebar-footer { grid-template-columns: repeat(4, minmax(0,1fr)); gap: 4px; }.chat-sidebar-footer a { display: flex; flex-direction: column; gap: 4px; padding: 7px 3px; font-size: 10px; text-align: center; }.chat-topbar { padding: 17px 18px; } }
</style>

<style scoped>
.session-row { display: flex; align-items: center; gap: 2px; }
.session-row .session-link { flex: 1; min-width: 0; }
.session-archive { width: 26px; height: 26px; border: 0; border-radius: 6px; color: #72776f; background: transparent; cursor: pointer; }
.session-archive:hover { color: #e0b199; background: rgba(255,255,255,.07); }
.session-empty.error { color: #d6937b; }
</style>
