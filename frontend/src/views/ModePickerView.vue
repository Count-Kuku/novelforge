<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'

const workspace = useWorkspaceStore()
const router = useRouter()
const hasProject = computed(() => Boolean(workspace.activeProjectId))
const projectName = ref('')
const storyName = ref('')
const creationMode = ref<'planned' | 'conversational'>('planned')
const creating = ref(false)
const enteringMode = ref<'planned' | 'conversational' | ''>('')
const error = ref('')
const projectInput = ref<HTMLInputElement | null>(null)

async function enterMode(mode: 'planned' | 'conversational') {
  if (enteringMode.value) return
  enteringMode.value = mode
  error.value = ''
  try {
    // The router guard keeps the active story and URL mode consistent. When a
    // user enters from the picker, persist the selected mode first so the
    // guard does not immediately redirect back to the previous workbench.
    if (!workspace.ready) await workspace.load()
    if (!workspace.activeProjectId) {
      creationMode.value = mode
      await nextTick()
      projectInput.value?.focus()
      return
    }
    if (workspace.activeProjectId && workspace.activeStory && workspace.mode !== mode) {
      await workspace.setMode(mode)
    }
    await router.push(mode === 'conversational' ? '/conversational' : '/planned')
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '进入工作台失败'
  } finally {
    enteringMode.value = ''
  }
}

async function createWorkspace() {
  if (!projectName.value.trim() || !storyName.value.trim()) return
  creating.value = true
  error.value = ''
  try {
    const project = await api.createProject({ name: projectName.value.trim(), title: projectName.value.trim() })
    const story = await api.createStory(project.project.project_id, { name: storyName.value.trim(), creation_mode: creationMode.value })
    await workspace.load()
    await workspace.selectProject(project.project.project_id)
    await workspace.selectStory(story.story.story_id)
    await router.push(creationMode.value === 'conversational' ? '/conversational' : '/planned')
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '创建工作区失败'
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <main class="picker-page">
    <div class="picker-glow"></div>
    <header class="picker-header"><div class="picker-logo">N</div><div><strong>NovelForge</strong><span>本地小说创作工作台</span></div><span class="header-status"><i></i>本地运行</span></header>
    <section class="picker-content">
      <p class="eyebrow">选择工作方式</p>
      <h1>选择本次要进入的<em>工作台</em></h1>
      <p class="picker-intro">规划工作台适合按层级推进长篇；对话工作台适合快速讨论和试写。两者共用同一套项目数据。</p>
      <div class="mode-grid">
        <a href="/planned" class="mode-card planned-card" :class="{ selected: !hasProject && creationMode === 'planned' }" :aria-busy="enteringMode === 'planned'" @click.prevent="enterMode('planned')">
          <div class="card-icon">⌘</div><span class="card-label">适合长篇规划</span><h2>按层级规划<br /><i>结构与章节</i></h2><p>集中管理创作方向、全书大纲、分卷、剧情段和章节正文，适合持续推进的长篇项目。</p><div class="card-footer"><span>{{ hasProject ? '进入规划工作台' : '选择规划模式' }}</span><b>→</b></div>
        </a>
        <a href="/conversational" class="mode-card conversational-card" :class="{ selected: !hasProject && creationMode === 'conversational' }" :aria-busy="enteringMode === 'conversational'" @click.prevent="enterMode('conversational')">
          <div class="card-icon">✦</div><span class="card-label">适合讨论与试写</span><h2>从对话开始<br /><i>写作或修改</i></h2><p>直接输入想法、写作要求或待修改文本，再按需保存版本、附件和提炼出的知识。</p><div class="card-footer"><span>{{ hasProject ? '进入对话工作台' : '选择对话模式' }}</span><b>→</b></div>
        </a>
      </div>
      <div v-if="workspace.loading || !workspace.ready" class="picker-loading">正在读取本地项目…</div>
      <div v-else-if="!hasProject" class="setup-panel"><div><p class="eyebrow">首次使用</p><h3>创建项目和第一个故事</h3><p>名称和工作模式之后都可以修改。</p></div><div class="setup-fields"><input ref="projectInput" v-model="projectName" aria-label="项目名称" placeholder="项目名称" /><input v-model="storyName" aria-label="故事名称" placeholder="第一个故事名称" /><div class="mode-choice" aria-label="初始工作模式"><button type="button" :class="{ selected: creationMode === 'planned' }" @click="creationMode = 'planned'">规划</button><button type="button" :class="{ selected: creationMode === 'conversational' }" @click="creationMode = 'conversational'">对话</button></div><button class="button accent" :disabled="creating || !projectName.trim() || !storyName.trim()" @click="createWorkspace">{{ creating ? '正在创建…' : '创建并进入' }}</button></div><p v-if="error" class="setup-error">{{ error }}</p></div><p v-if="error && hasProject" class="picker-error">{{ error }}</p><p class="picker-footnote">{{ hasProject ? `当前项目：${workspace.activeProject?.title || workspace.activeProject?.name}` : '项目数据保存在当前设备。' }}</p>
    </section>
  </main>
</template>

<style scoped>
.picker-page { position: relative; min-height: 100vh; overflow: hidden; color: #2c2a27; background: #f4f0e8; }.picker-glow { position: absolute; top: -300px; left: 50%; width: 760px; height: 560px; border-radius: 50%; background: radial-gradient(ellipse, rgba(220,153,119,.17), transparent 68%); transform: translateX(-50%); pointer-events: none; }.picker-header { position: relative; z-index: 1; display: flex; align-items: center; gap: 11px; max-width: 1220px; margin: 0 auto; padding: 28px 32px; }.picker-logo { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 11px; color: #fff7ef; background: #c45c3a; font-family: Georgia, serif; font-size: 20px; }.picker-header strong { display: block; font-family: Georgia, serif; font-size: 17px; }.picker-header span { display: block; margin-top: 2px; color: #8b8177; font-size: 11px; }.header-status { display: flex; align-items: center; gap: 7px; margin-left: auto; }.header-status i { width: 6px; height: 6px; border-radius: 50%; background: #819477; }.picker-content { position: relative; z-index: 1; max-width: 1050px; margin: clamp(60px, 12vh, 132px) auto 0; padding: 0 28px 60px; text-align: center; }.picker-content h1 { margin: 0; font-family: Georgia, serif; font-size: clamp(42px, 7vw, 78px); font-weight: 400; letter-spacing: -.055em; line-height: 1.08; }.picker-content h1 em { color: #bd6444; font-style: normal; }.picker-intro { max-width: 570px; margin: 24px auto 53px; color: #847a6f; font-size: 15px; line-height: 1.8; }.mode-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 19px; text-align: left; }.mode-card { position: relative; display: flex; min-height: 356px; flex-direction: column; padding: 29px 30px 24px; border: 1px solid rgba(58,48,39,.12); border-radius: 23px; box-shadow: 0 15px 45px rgba(78,57,38,.07); transition: transform .25s ease, box-shadow .25s ease; }.mode-card:hover { transform: translateY(-5px); box-shadow: 0 25px 60px rgba(78,57,38,.13); }.planned-card { background: #fffaf2; }.conversational-card { color: #e9e5de; border-color: rgba(255,255,255,.08); background: #292b2a; }.card-icon { display: grid; place-items: center; width: 40px; height: 40px; margin-bottom: 25px; border-radius: 13px; color: #bc6242; background: #f2dfd4; font-size: 19px; }.conversational-card .card-icon { color: #e2ae8f; background: rgba(218,157,124,.15); }.card-label { margin-bottom: 16px; color: #ad9b8b; font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }.mode-card h2 { margin: 0; font-family: Georgia, serif; font-size: 30px; font-weight: 400; letter-spacing: -.03em; line-height: 1.16; }.mode-card h2 i { color: #c45c3a; font-style: normal; }.conversational-card h2 i { color: #e3a784; }.mode-card p { max-width: 390px; margin: auto 0 25px; color: #8c8176; font-size: 13px; line-height: 1.75; }.conversational-card p { color: #9a9c94; }.card-footer { display: flex; align-items: center; justify-content: space-between; padding-top: 17px; border-top: 1px solid rgba(58,48,39,.1); color: #60564d; font-size: 12px; }.conversational-card .card-footer { border-color: rgba(255,255,255,.11); color: #c9b9aa; }.card-footer b { color: #bd6444; font-size: 21px; font-weight: 400; }.picker-footnote { margin: 26px 0 0; color: #9b9084; font-size: 12px; }.setup-panel { display: grid; grid-template-columns: 1fr 1.15fr; gap: 24px; margin: 32px auto 0; padding: 22px 24px; border: 1px solid rgba(58,48,39,.12); border-radius: 18px; text-align: left; background: rgba(255,253,249,.72); }.setup-panel h3 { margin: 8px 0; font-family: Georgia, serif; font-size: 22px; font-weight: 400; }.setup-panel p:not(.eyebrow):not(.setup-error) { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.7; }.setup-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }.setup-fields input { width: 100%; min-width: 0; padding: 11px 12px; border: 1px solid var(--line); border-radius: 10px; outline: none; color: var(--ink); background: #fffdf9; font-size: 13px; }.setup-fields input:focus { border-color: #c88468; box-shadow: 0 0 0 3px rgba(200,132,104,.12); }.mode-choice { display: flex; gap: 6px; }.mode-choice button { flex: 1; border: 1px solid var(--line); border-radius: 9px; color: var(--muted); background: transparent; font-size: 12px; }.mode-choice button.selected { color: #a95539; border-color: #d39a83; background: #f6e3d9; }.setup-fields .button { grid-column: 1 / -1; }.setup-error { grid-column: 1 / -1; margin: 0; color: #b55f46; font-size: 12px; }
.picker-header span { color: #6b6259; }.header-status { color: #6b6259; }.picker-content h1 em { color: #8c412e; }.picker-intro { color: #675e55; }.card-icon { color: #8e3e28; }.card-label { color: #74665b; }.conversational-card .card-label { color: #c9b9aa; }.mode-card h2 i { color: #8c412e; }.conversational-card h2 i { color: #e3a784; }.mode-card p { color: #6f655b; }.conversational-card p { color: #b5b8b0; }.card-footer { color: #51483f; }.card-footer b { color: #8c412e; }.picker-footnote { color: #6d6258; }.setup-panel .eyebrow { color: #62594f; }.setup-panel p:not(.eyebrow):not(.setup-error) { color: #6d6359; }.mode-choice button { color: #6d6359; }.mode-choice button.selected { color: #8c412e; }.setup-error, .picker-error { color: #9f4d3e; }.picker-error { margin: 18px 0 0; font-size: 12px; }
.mode-card.selected { outline: 3px solid rgba(169,75,47,.24); outline-offset: 3px; }.picker-loading { margin: 28px auto 0; color: #786e65; font-size: 12px; }
@media (max-width: 720px) { .picker-header { padding: 20px; }.picker-content { margin-top: 55px; padding: 0 18px 42px; }.picker-intro { margin-bottom: 32px; }.mode-grid { grid-template-columns: 1fr; }.mode-card { min-height: 300px; }.setup-panel { grid-template-columns: 1fr; }.setup-fields { grid-template-columns: 1fr; }.setup-fields .button { grid-column: auto; } }
</style>
