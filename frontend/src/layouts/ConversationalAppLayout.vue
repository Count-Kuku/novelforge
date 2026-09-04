<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { useWorkspaceStore } from '../stores/workspace'
import { api } from '../api/client'
import type { CreativeSession } from '../types'
import { dialog } from '../ui/dialog'
import { notify } from '../ui/notifications'
import { clearAllEditorDirty, hasDirtyEditors } from '../ui/dirty'

const workspace = useWorkspaceStore()
const route = useRoute()
const viewKey = computed(() => `${workspace.activeProjectId}:${workspace.activeStoryId}:${route.fullPath}`)
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

async function changeProject(event: Event) {
  if (hasDirtyEditors.value && !await dialog.confirm({ title: '放弃未保存修改？', message: '切换项目会重新加载当前页面，尚未保存的修改将丢失。', confirmLabel: '继续切换', tone: 'danger' })) return
  clearAllEditorDirty()
  await workspace.selectProject((event.target as HTMLSelectElement).value)
}

async function changeStory(event: Event) {
  if (hasDirtyEditors.value && !await dialog.confirm({ title: '放弃未保存修改？', message: '切换故事会重新加载当前页面，尚未保存的修改将丢失。', confirmLabel: '继续切换', tone: 'danger' })) return
  clearAllEditorDirty()
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

function sessionStatusLabel(status: string) {
  return ({ active: '进行中', archived: '已归档', completed: '已完成' } as Record<string, string>)[status] || status
}
</script>

<template>
  <div class="chat-shell">
    <aside class="chat-sidebar">
      <div class="chat-brand"><div class="orb"></div><div><strong>NovelForge</strong><small>对话工作台</small></div></div>
      <div class="chat-context"><span class="context-label">当前故事</span><select class="chat-story-select" :value="workspace.activeStoryId" aria-label="选择故事" @change="changeStory"><option v-if="!workspace.activeStories.length" value="">暂无进行中的故事</option><option v-for="story in workspace.activeStories" :key="story.story_id" :value="story.story_id">{{ story.name }}</option></select><label class="chat-project-select"><span>{{ projectLabel }}</span><select :value="workspace.activeProjectId" aria-label="选择项目" @change="changeProject"><option v-for="project in workspace.projects" :key="project.project_id" :value="project.project_id">{{ project.title || project.name }}</option></select></label></div>
      <RouterLink class="new-chat" to="/conversational"><span>＋</span>新建创作会话</RouterLink>
      <div class="session-list"><p class="eyebrow">最近会话</p><div v-if="sessionError" class="session-empty error">{{ sessionError }}</div><template v-else><div v-for="session in sessions" :key="session.session_id" class="session-row"><RouterLink class="session-link" :to="{ name: 'conversational-session', params: { sessionId: session.session_id } }">{{ session.title || session.session_goal }}<small>{{ sessionStatusLabel(session.status) }}</small></RouterLink><button v-if="session.status !== 'archived'" class="session-archive" aria-label="归档会话" title="归档会话" @click="archiveSession(session)">···</button></div><div v-if="!sessions.length" class="session-empty">暂无会话。<br />点击上方按钮开始一次写作或讨论。</div></template></div>
      <nav class="chat-sidebar-footer" aria-label="对话工作台主导航"><RouterLink to="/conversational" :class="{ active: route.name === 'conversational-home' || route.name === 'conversational-session' }"><span>✦</span>对话</RouterLink><RouterLink to="/conversational/works" active-class="active"><span>▤</span>作品</RouterLink><RouterLink to="/conversational/library" active-class="active"><span>▦</span>资料库</RouterLink><RouterLink to="/conversational/settings" active-class="active"><span>⚙</span>设置</RouterLink></nav>
    </aside>
    <main class="chat-main"><header class="chat-topbar"><div class="mode-badge"><i></i>自由对话</div><div class="chat-top-actions"><span class="live-dot"></span>本地工作区 <span class="chat-avatar" aria-hidden="true">NF</span></div></header><RouterView :key="viewKey" /></main>
  </div>
</template>

<style scoped>
.chat-shell { --ink: #e8e3dc; --muted: #b3aea6; --line: rgba(255,255,255,.13); --paper: #2f312f; --paper-strong: #363936; --accent: #e0a17d; --accent-soft: rgba(224,161,125,.15); --sage: #8eaa82; display: grid; grid-template-columns: 302px 1fr; min-height: 100vh; color: #e8e3dc; color-scheme: dark; background: #252625; }.chat-sidebar { position: sticky; top: 0; display: flex; flex-direction: column; align-self: start; gap: 24px; height: 100vh; height: 100dvh; min-height: 0; overflow: hidden; padding: 28px 22px 20px; border-right: 1px solid rgba(255,255,255,.08); background: #202120; }.chat-brand, .chat-context, .new-chat { flex: 0 0 auto; }.chat-brand { display: flex; align-items: center; gap: 11px; }.chat-brand strong { display: block; color: #f0ece5; font-family: Georgia, serif; font-size: 17px; }.chat-brand small { display: block; margin-top: 3px; color: #a2a69f; font-size: 11px; }.orb { width: 33px; height: 33px; border: 6px solid #bd7659; border-right-color: #dfb795; border-radius: 50%; transform: rotate(-32deg); }.chat-context { display: grid; gap: 5px; padding: 18px; border: 1px solid rgba(255,255,255,.08); border-radius: 16px; background: #292b29; }.context-label { color: #969992; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }.chat-story-select, .chat-project-select select { width: 100%; overflow: hidden; border: 0; outline: 0; color: #f2eee7; background: transparent; font-family: Georgia, serif; font-size: 17px; text-overflow: ellipsis; white-space: nowrap; }.chat-story-select option, .chat-project-select option { color: #ece7df; background: #292b2a; }.chat-story-select option:checked, .chat-project-select option:checked { color: #fff4ea; background: #6a493c; font-weight: 600; }.chat-project-select { display: flex; align-items: center; gap: 5px; color: #a6aaa3; font-size: 12px; }.chat-project-select select { flex: 1; color: #a6aaa3; font-family: inherit; font-size: 12px; }.new-chat { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 12px; border: 1px solid rgba(222,172,139,.45); border-radius: 11px; color: #e8c5ae; background: rgba(190,111,78,.12); font-size: 13px; }.new-chat span { font-size: 18px; }.session-list { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding-right: 4px; scrollbar-gutter: stable; }.session-list .eyebrow { color: #a6aaa3; }.session-link { display: flex; flex-direction: column; gap: 4px; padding: 9px 8px; border-radius: 9px; color: #c9c6bc; font-size: 12px; }.session-link:hover { background: rgba(255,255,255,.06); }.session-link small { color: #959b93; font-size: 10px; }.session-empty { padding: 12px 4px; color: #a2a69f; font-size: 12px; line-height: 1.8; }.chat-sidebar-footer { display: grid; flex: 0 0 auto; gap: 5px; padding-top: 13px; border-top: 1px solid rgba(255,255,255,.08); }.chat-sidebar-footer a { display: grid; grid-template-columns: 24px minmax(0,1fr); align-items: center; gap: 8px; padding: 8px 9px; border-radius: 8px; color: #a2a69f; font-size: 12px; }.chat-sidebar-footer a:hover { color: #d9d3ca; background: rgba(255,255,255,.045); }.chat-sidebar-footer a.active { color: #e7bea6; background: rgba(211,131,97,.1); }.chat-sidebar-footer a span { color: #d08b6e; text-align: center; }.chat-main { min-width: 0; background: radial-gradient(circle at 62% 0, rgba(148,119,94,.13), transparent 36%), #292b2a; }.chat-topbar { display: flex; align-items: center; justify-content: space-between; padding: 22px clamp(22px, 5vw, 70px); border-bottom: 1px solid rgba(255,255,255,.07); }.mode-badge { display: flex; align-items: center; gap: 8px; color: #d8c8b7; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }.mode-badge i, .live-dot { width: 7px; height: 7px; border-radius: 50%; background: #d38361; box-shadow: 0 0 0 4px rgba(211,131,97,.12); }.chat-top-actions { display: flex; align-items: center; gap: 12px; color: #a2a69f; font-size: 12px; }.live-dot { width: 5px; height: 5px; background: #8baa74; box-shadow: none; }.chat-avatar { display: grid; place-items: center; width: 34px; height: 34px; border: 1px solid rgba(255,255,255,.14); border-radius: 50%; color: #d9d2c9; background: #363936; font-size: 10px; }
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
