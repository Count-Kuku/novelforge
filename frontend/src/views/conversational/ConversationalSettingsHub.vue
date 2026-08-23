<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import SettingsView from '../SettingsView.vue'
import RulesView from '../RulesView.vue'
import { api } from '../../api/client'
import { useWorkspaceStore } from '../../stores/workspace'
import { dialog } from '../../ui/dialog'
import { notify } from '../../ui/notifications'
import { clearAllEditorDirty, hasDirtyEditors } from '../../ui/dirty'

const workspace = useWorkspaceStore()
const route = useRoute()
const router = useRouter()
const busyStoryId = ref('')
const validSections = new Set(['models', 'rules', 'workspace'])
const activeSection = computed(() => {
  const section = String(route.query.section || 'models')
  return validSections.has(section) ? section : 'models'
})

function sectionLink(section: string) {
  return { name: 'conversational-settings', query: section === 'models' ? {} : { section } }
}

async function switchToPlan() {
  if (hasDirtyEditors.value && !await dialog.confirm({ title: '放弃未保存修改？', message: '切换工作台会重新加载当前页面，尚未保存的修改将丢失。', confirmLabel: '继续切换', tone: 'danger' })) return
  clearAllEditorDirty()
  await workspace.setMode('planned')
  await router.push('/planned')
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

async function restoreArchivedStory(storyId: string) {
  if (!workspace.activeProjectId || busyStoryId.value) return
  busyStoryId.value = storyId
  try {
    const result = await api.restoreStory(workspace.activeProjectId, storyId)
    if (!result.restored) throw new Error('这个故事已经不存在')
    await workspace.loadStories()
    await workspace.selectStory(storyId)
    notify('故事已恢复', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '故事恢复失败', 'error') }
  finally { busyStoryId.value = '' }
}

async function deleteArchivedStory(story: { story_id: string; name: string }) {
  if (!workspace.activeProjectId || busyStoryId.value) return
  const confirmation = await dialog.prompt({ title: '永久删除故事？', message: '故事中的作品、对话、资料和设置都会被彻底删除，无法恢复。', confirmLabel: '永久删除', tone: 'danger', input: { label: '输入故事名称确认', match: story.name } })
  if (confirmation !== story.name) return
  busyStoryId.value = story.story_id
  try {
    const result = await api.deleteStory(workspace.activeProjectId, story.story_id)
    if (!result.deleted) throw new Error('这个故事已经不存在')
    await workspace.loadStories()
    notify('故事已永久删除', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '故事删除失败', 'error') }
  finally { busyStoryId.value = '' }
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
</script>

<template>
  <div class="settings-hub">
    <nav class="settings-hub-nav" aria-label="设置分类">
      <RouterLink :to="sectionLink('models')" :class="{ active: activeSection === 'models' }"><span>⚙</span><strong>模型与能力</strong><small>模型、凭据、费用和本地能力</small></RouterLink>
      <RouterLink :to="sectionLink('rules')" :class="{ active: activeSection === 'rules' }"><span>≡</span><strong>规则与提示词</strong><small>生成规则、写作偏好和提示词</small></RouterLink>
      <RouterLink :to="sectionLink('workspace')" :class="{ active: activeSection === 'workspace' }"><span>⌘</span><strong>项目与故事</strong><small>工作台切换、归档和删除</small></RouterLink>
    </nav>
    <SettingsView v-if="activeSection === 'models'" />
    <RulesView v-else-if="activeSection === 'rules'" />
    <section v-else class="workspace-settings">
      <p class="eyebrow">项目与故事</p>
      <h1>管理当前<em>写作空间</em></h1>
      <p class="intro">低频且影响范围较大的操作集中在这里，避免打断日常对话。</p>
      <article class="workspace-card"><div><small>当前项目</small><strong>{{ workspace.activeProject?.title || workspace.activeProject?.name || '未选择项目' }}</strong><span>{{ workspace.activeStory?.name || '暂无进行中的故事' }}</span></div><button class="button secondary" @click="switchToPlan">切换到规划工作台</button></article>
      <article class="archive-manager">
        <div class="archive-heading"><div><p class="eyebrow">已归档故事</p><h2>保留，或彻底清理</h2></div><span>{{ workspace.archivedStories.length }} 个</span></div>
        <p v-if="!workspace.archivedStories.length" class="archive-empty">归档后的故事会出现在这里，你可以随时恢复或永久删除。</p>
        <ul v-else class="archive-list">
          <li v-for="story in workspace.archivedStories" :key="story.story_id"><div><strong>{{ story.name }}</strong><small>{{ story.description || '没有故事说明' }}</small></div><div><button :disabled="Boolean(busyStoryId)" @click="restoreArchivedStory(story.story_id)">{{ busyStoryId === story.story_id ? '处理中…' : '恢复' }}</button><button class="critical" :disabled="Boolean(busyStoryId)" @click="deleteArchivedStory(story)">永久删除</button></div></li>
        </ul>
      </article>
      <article class="danger-zone"><div><p class="eyebrow">谨慎操作</p><h2>归档与删除</h2><p>归档当前故事后，可在上方恢复或永久删除；删除项目会连同项目内全部故事与本地资产一起移除。</p></div><div><button class="danger-button" :disabled="!workspace.activeStory" @click="archiveStory">归档当前故事</button><button class="danger-button critical" @click="deleteProject">删除项目</button></div></article>
    </section>
  </div>
</template>

<style scoped>
.settings-hub { padding: 24px clamp(22px, 5vw, 70px) 0; }.settings-hub-nav { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px; max-width: 940px; margin: 0 auto 30px; }.settings-hub-nav a { display: grid; grid-template-columns: 25px minmax(0,1fr); gap: 2px 8px; padding: 13px 14px; border: 1px solid var(--line); border-radius: 11px; color: var(--muted); background: rgba(255,255,255,.025); }.settings-hub-nav a.active { color: var(--ink); border-color: rgba(211,131,97,.4); background: rgba(211,131,97,.09); }.settings-hub-nav a > span { grid-row: 1 / 3; align-self: center; color: var(--accent); }.settings-hub-nav strong { font-size: 12px; font-weight: 500; }.settings-hub-nav small { overflow: hidden; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }.workspace-settings { max-width: 940px; margin: 0 auto; padding: 12px 0 60px; }.workspace-settings h1 { margin: 10px 0 16px; font-family: Georgia, serif; font-size: clamp(38px,5vw,62px); font-weight: 400; letter-spacing: -.055em; }.workspace-settings h1 em { color: var(--accent); font-style: normal; }.intro { color: var(--muted); font-size: 13px; }.workspace-card { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-top: 36px; padding: 24px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }.workspace-card small, .workspace-card strong, .workspace-card span { display: block; }.workspace-card small { color: var(--muted); font-size: 10px; }.workspace-card strong { margin-top: 5px; font-family: Georgia, serif; font-size: 23px; font-weight: 400; }.workspace-card span { margin-top: 5px; color: var(--muted); font-size: 11px; }.archive-manager { margin-top: 18px; padding: 24px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.035); }.archive-heading { display: flex; align-items: end; justify-content: space-between; gap: 16px; }.archive-heading h2 { margin: 5px 0 0; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.archive-heading > span, .archive-empty { color: var(--muted); font-size: 11px; }.archive-empty { margin: 18px 0 0; }.archive-list { display: grid; gap: 8px; margin: 18px 0 0; padding: 0; list-style: none; }.archive-list li { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 13px 14px; border: 1px solid var(--line); border-radius: 11px; background: rgba(0,0,0,.08); }.archive-list strong, .archive-list small { display: block; }.archive-list strong { color: var(--ink); font-size: 12px; font-weight: 500; }.archive-list small { margin-top: 4px; color: var(--muted); font-size: 10px; }.archive-list li > div:last-child { display: flex; gap: 7px; }.archive-list button { padding: 7px 10px; border: 1px solid var(--line); border-radius: 8px; color: var(--ink); background: rgba(255,255,255,.035); font-size: 10px; }.archive-list button.critical { color: #f1b29f; border-color: rgba(209,104,81,.32); background: rgba(166,66,47,.13); }.archive-list button:disabled, .danger-button:disabled { opacity: .45; cursor: not-allowed; }.danger-zone { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-top: 18px; padding: 24px; border: 1px solid rgba(209,104,81,.28); border-radius: 16px; background: rgba(158,66,49,.06); }.danger-zone h2 { margin: 5px 0 8px; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.danger-zone p:not(.eyebrow) { max-width: 560px; margin: 0; color: var(--muted); font-size: 11px; line-height: 1.7; }.danger-zone > div:last-child { display: flex; gap: 8px; }.danger-button { padding: 9px 13px; border: 1px solid rgba(209,104,81,.32); border-radius: 9px; color: #d8a08f; background: transparent; font-size: 11px; }.danger-button.critical { color: #f1b29f; background: rgba(166,66,47,.16); }
@media (max-width: 720px) { .settings-hub { padding-inline: 16px; }.settings-hub-nav { grid-template-columns: 1fr; }.workspace-card, .danger-zone, .archive-list li { align-items: flex-start; flex-direction: column; }.danger-zone > div:last-child { flex-wrap: wrap; } }
</style>
