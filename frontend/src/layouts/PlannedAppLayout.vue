<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useWorkspaceStore } from '../stores/workspace'
import { api } from '../api/client'
import { dialog } from '../ui/dialog'
import { notify } from '../ui/notifications'

const workspace = useWorkspaceStore()
const router = useRouter()
const structure = ref<{ volumes: any[]; arcs: any[]; chapters: any[] }>({ volumes: [], arcs: [], chapters: [] })
const structureOpen = ref(true)
const structureError = ref('')

async function loadStructure() {
  structureError.value = ''
  if (!workspace.activeProjectId || !workspace.activeStory) { structure.value = { volumes: [], arcs: [], chapters: [] }; return }
  try { structure.value = await api.structure(workspace.activeProjectId, workspace.activeStory.story_id) } catch (reason) { structure.value = { volumes: [], arcs: [], chapters: [] }; structureError.value = reason instanceof Error ? reason.message : '结构读取失败' }
}

async function switchToConversation() {
  await workspace.setMode('conversational')
  await router.push('/conversational')
}

async function changeProject(event: Event) {
  await workspace.selectProject((event.target as HTMLSelectElement).value)
}

async function changeStory(event: Event) {
  await workspace.selectStory((event.target as HTMLSelectElement).value)
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

async function renameCurrentProject() {
  if (!workspace.activeProjectId || !workspace.activeProject) return
  const name = await dialog.prompt({ title: '重命名项目', confirmLabel: '保存', input: { label: '项目名称', initialValue: workspace.activeProject.name } })
  if (!name?.trim() || name.trim() === workspace.activeProject.name) return
  try {
    await api.renameProject(workspace.activeProjectId, name.trim())
    await workspace.load()
    notify('项目名称已更新', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '项目重命名失败', 'error') }
}

async function archiveCurrentStory() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  if (!await dialog.confirm({ title: '归档当前故事？', message: `“${workspace.activeStory.name}”将从当前故事列表中移除，数据仍保留在本地数据库中。`, confirmLabel: '归档故事', tone: 'danger' })) return
  try {
    await api.archiveStory(workspace.activeProjectId, workspace.activeStory.story_id)
    await workspace.loadStories()
    notify('故事已归档', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '故事归档失败', 'error') }
}

async function deleteCurrentProject() {
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

onMounted(loadStructure)
watch(() => [workspace.activeProjectId, workspace.activeStoryId], loadStructure)
</script>

<template>
  <div class="planned-shell">
    <aside class="planned-rail">
      <div class="brand-mark"><span>N</span><div><strong>NovelForge</strong><small>规划工作台</small></div></div>
      <label class="rail-project"><span class="dot"></span><select :value="workspace.activeProjectId" aria-label="选择项目" @change="changeProject"><option v-for="project in workspace.projects" :key="project.project_id" :value="project.project_id">{{ project.title || project.name }}</option></select><span class="chevron">⌄</span></label>
      <nav class="planned-nav" aria-label="规划导航">
        <p class="eyebrow">规划流程</p>
        <RouterLink to="/planned/direction" active-class="active"><span>✦</span>创作方向</RouterLink>
        <RouterLink to="/planned/outline" active-class="active"><span>⌁</span>结构与大纲</RouterLink>
        <RouterLink to="/planned/chapters" active-class="active"><span>▤</span>章节推进</RouterLink>
        <RouterLink to="/planned/workspace" active-class="active"><span>⌂</span>共享工作区</RouterLink><RouterLink to="/planned/workspace/content" active-class="active"><span>▦</span>内容浏览</RouterLink><RouterLink to="/planned/workspace/entities" active-class="active"><span>◎</span>实体与时间线</RouterLink><RouterLink to="/planned/workspace/graph" active-class="active"><span>◇</span>关系图</RouterLink><RouterLink to="/planned/workspace/research" active-class="active"><span>⌁</span>网络研究</RouterLink>
      </nav>
      <div class="structure-tree"><button class="tree-heading" @click="structureOpen = !structureOpen"><span>作品结构</span><small>{{ structure.chapters.length }} 章</small><b>{{ structureOpen ? '⌃' : '⌄' }}</b></button><div v-if="structureOpen" class="tree-body"><div v-if="structureError" class="tree-empty error">{{ structureError }}</div><div v-else-if="!structure.volumes.length && !structure.chapters.length" class="tree-empty">结构会在保存后出现</div><RouterLink v-for="volume in structure.volumes" :key="volume.volume_no" :to="`/planned/volumes/${volume.volume_no}`" class="tree-node volume">卷 {{ volume.volume_no }} · {{ volume.title || '未命名' }}</RouterLink><div v-for="chapter in structure.chapters.slice(0, 8)" :key="chapter.chapter_no" class="tree-node"><RouterLink to="/planned/chapters">{{ String(chapter.chapter_no).padStart(2, '0') }} {{ chapter.title || '未命名章节' }}</RouterLink></div><div v-if="structure.chapters.length > 8" class="tree-more">还有 {{ structure.chapters.length - 8 }} 章…</div></div></div>
      <div class="rail-footer"><RouterLink to="/"><span>⇄</span>切换工作台</RouterLink><RouterLink to="/planned/settings"><span>⚙</span>能力与设置</RouterLink><RouterLink to="/planned/rules"><span>≡</span>规则与偏好</RouterLink><button class="rail-action" @click="renameCurrentStory"><span>✎</span>重命名故事</button><button class="rail-action" @click="renameCurrentProject"><span>⌘</span>重命名项目</button><button class="rail-action danger" @click="archiveCurrentStory"><span>□</span>归档当前故事</button><button class="rail-action danger" @click="deleteCurrentProject"><span>×</span>删除项目</button></div>
    </aside>
    <main class="planned-main">
      <header class="planned-topbar"><div><p class="eyebrow">当前故事</p><div class="title-line"><select class="story-switcher" :value="workspace.activeStoryId" aria-label="选择故事" @change="changeStory"><option v-for="story in workspace.stories" :key="story.story_id" :value="story.story_id">{{ story.name }}</option></select></div></div><div class="top-actions"><button class="mode-toggle" @click="switchToConversation">切到对话工作台</button><span class="pill">规划模式</span><span class="avatar" aria-hidden="true">NF</span></div></header>
      <section v-if="workspace.error" class="connection-banner">{{ workspace.error }}<span>请确认 NovelForge 本地服务正在运行。</span></section>
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.planned-shell { display: grid; grid-template-columns: 266px 1fr; min-height: 100vh; background: radial-gradient(circle at 80% -20%, #fff8ee 0, transparent 42%), #f4f0e8; }
.planned-rail { display: flex; flex-direction: column; gap: 24px; padding: 30px 22px 22px; border-right: 1px solid var(--line); background: rgba(247,243,235,.82); }
.brand-mark { display: flex; align-items: center; gap: 10px; }.brand-mark > span { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 11px; color: #fff8ef; background: var(--accent); font-family: Georgia, serif; font-size: 20px; }.brand-mark strong { display: block; font-family: Georgia, serif; font-size: 17px; }.brand-mark small { display: block; margin-top: 2px; color: var(--muted); font-size: 11px; }
.rail-project { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border: 1px solid var(--line); border-radius: 13px; color: #5f574e; background: rgba(255,255,255,.5); font-size: 13px; }.rail-project select, .story-switcher { min-width: 0; overflow: hidden; border: 0; outline: 0; color: inherit; background: transparent; text-overflow: ellipsis; white-space: nowrap; }.rail-project select { flex: 1; font-size: 13px; }.rail-project select option, .story-switcher option { color: var(--ink); }.dot { width: 7px; height: 7px; border-radius: 50%; background: var(--sage); }.chevron { margin-left: auto; color: var(--muted); }.title-line { display: flex; align-items: center; }.story-switcher { max-width: 500px; font-family: Georgia, serif; font-size: clamp(28px, 3vw, 42px); font-weight: 500; letter-spacing: -.03em; }
.planned-nav { display: grid; gap: 7px; }.planned-nav a, .rail-footer a { display: flex; align-items: center; gap: 12px; padding: 12px 13px; border-radius: 12px; color: #756c62; font-size: 14px; }.planned-nav a span, .rail-footer a span { width: 17px; color: #aa9d8e; text-align: center; }.planned-nav a:hover, .planned-nav a.active { color: var(--ink); background: #e9e1d6; }.planned-nav a.active span { color: var(--accent); }
.structure-tree { margin-top: 5px; padding-top: 16px; border-top: 1px solid var(--line); }.tree-heading { display: grid; grid-template-columns: 1fr auto auto; align-items: center; width: 100%; gap: 8px; padding: 0 7px 8px; border: 0; color: #756c62; background: transparent; cursor: pointer; font: inherit; font-size: 11px; text-align: left; }.tree-heading small { color: #aa9d8e; font-size: 10px; }.tree-heading b { color: #aa9d8e; font-weight: 400; }.tree-body { display: grid; gap: 3px; max-height: 185px; overflow: auto; padding: 2px 4px; }.tree-node, .tree-empty, .tree-more { padding: 5px 6px; color: #95897d; font-size: 10px; }.tree-node a { color: inherit; }.tree-node a:hover { color: var(--accent); }.tree-node.volume { color: #6f6256; font-weight: 600; }.tree-more { color: #b0a298; }
.tree-empty.error { color: #a44f47; }
.rail-footer { display: grid; gap: 3px; margin-top: auto; border-top: 1px solid var(--line); padding-top: 16px; }.rail-footer a { font-size: 12px; }
.rail-action { display: flex; align-items: center; gap: 12px; padding: 10px 13px; border: 0; border-radius: 12px; color: #756c62; background: transparent; cursor: pointer; font: inherit; font-size: 12px; text-align: left; }.rail-action span { width: 17px; color: #aa9d8e; text-align: center; }.rail-action:hover { color: var(--ink); background: #e9e1d6; }.rail-action.danger:hover { color: #a44f47; background: #faece8; }
.planned-main { min-width: 0; padding: 30px clamp(26px, 5vw, 72px) 72px; }.planned-topbar { display: flex; align-items: flex-start; justify-content: space-between; margin: 0 auto 38px; max-width: 1180px; }.planned-topbar h1 { margin: 0; font-family: Georgia, serif; font-size: clamp(28px, 3vw, 42px); font-weight: 500; letter-spacing: -.03em; }.top-actions { display: flex; align-items: center; gap: 12px; }.mode-toggle { border: 0; color: #9d6149; background: transparent; font-size: 12px; }.mode-toggle:hover { text-decoration: underline; }.avatar { display: grid; place-items: center; width: 38px; height: 38px; border: 1px solid var(--line); border-radius: 50%; color: var(--ink); background: #e9e0d4; font-size: 11px; font-weight: 700; }.connection-banner { max-width: 1180px; margin: -14px auto 24px; padding: 12px 16px; border: 1px solid #e9cbbd; border-radius: 12px; color: #7a4938; background: #fff1eb; font-size: 13px; }.connection-banner span { margin-left: 10px; opacity: .75; }
@media (max-width: 760px) { .planned-shell { grid-template-columns: 1fr; }.planned-rail { position: sticky; top: 0; z-index: 2; flex-direction: row; align-items: center; overflow-x: auto; padding: 12px 16px; }.rail-project, .rail-footer, .planned-nav .eyebrow { display: none; }.planned-nav { display: flex; }.planned-nav a { white-space: nowrap; }.planned-main { padding: 24px 18px 48px; } }
</style>
