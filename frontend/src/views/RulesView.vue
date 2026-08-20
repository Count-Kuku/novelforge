<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'

const workspace = useWorkspaceStore()
const globalJson = ref('{}')
const storyJson = ref('{}')
const projectJson = ref('{}')
const promptJson = ref('[]')
const autoConfig = ref<Record<string, unknown>>({})
const autoGoal = ref('')
const loading = ref(true)
const saving = ref(false)
const message = ref('')

function listText(value: unknown): string {
  return Array.isArray(value) ? value.map((item) => String(item)).join('、') : ''
}

async function load() {
  if (!workspace.activeProjectId || !workspace.activeStory) { loading.value = false; return }
  try {
    const [data, layers, options, auto] = await Promise.all([
      api.rules(workspace.activeProjectId, workspace.activeStory.story_id),
      api.settingsRules(workspace.activeProjectId, workspace.activeStory.story_id),
      api.promptOptions('story', workspace.activeProjectId, workspace.activeStory.story_id),
      api.autoConfiguration('chapter_write', workspace.activeProjectId, workspace.activeStory.story_id),
    ])
    storyJson.value = JSON.stringify(data.story || layers.story || {}, null, 2)
    projectJson.value = JSON.stringify(layers.project || data.project || {}, null, 2)
    globalJson.value = JSON.stringify(layers.global || {}, null, 2)
    promptJson.value = JSON.stringify(options.options || [], null, 2)
    autoConfig.value = auto.state || {}
  } catch (reason) { message.value = reason instanceof ApiClientError ? reason.message : '无法读取规则' } finally { loading.value = false }
}

async function save() {
  if (!workspace.activeProjectId || !workspace.activeStory || saving.value) return
  saving.value = true
  try {
    await api.updateSettingsRules('global', JSON.parse(globalJson.value), workspace.activeProjectId, workspace.activeStory.story_id)
    await api.updateSettingsRules('project', JSON.parse(projectJson.value), workspace.activeProjectId, workspace.activeStory.story_id)
    await api.updateRules(workspace.activeProjectId, workspace.activeStory.story_id, JSON.parse(storyJson.value))
    await api.updatePromptOptions('story', JSON.parse(promptJson.value), workspace.activeProjectId, workspace.activeStory.story_id)
    message.value = '规则与偏好已保存'
  } catch (reason) { message.value = reason instanceof Error ? reason.message : '规则保存失败' } finally { saving.value = false }
}

async function runAutoConfig() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  try { autoConfig.value = await api.configureAutoConfiguration('chapter_write', { goal: autoGoal.value }, workspace.activeProjectId, workspace.activeStory.story_id); message.value = '自动配置已更新，可查看原因与锁定字段' } catch (reason) { message.value = reason instanceof Error ? reason.message : '自动配置失败' }
}

onMounted(load)
</script>

<template>
  <section class="rules-page"><p class="eyebrow">RULES & PREFERENCES</p><h1>把创作边界，<em>写成可检查的规则。</em></h1><p class="intro">全局、项目、故事三层规则和提示词选项由服务端合并，自动配置展示原因和锁定字段。</p><div v-if="loading" class="rules-state">正在读取规则…</div><template v-else><div class="rules-grid"><article><div class="rules-head"><div><p class="eyebrow">GLOBAL</p><h2>全局规则</h2></div></div><textarea v-model="globalJson" aria-label="全局规则 JSON" rows="14"></textarea></article><article><div class="rules-head"><div><p class="eyebrow">PROJECT</p><h2>项目基线</h2></div></div><textarea v-model="projectJson" aria-label="项目规则 JSON" rows="14"></textarea></article><article><div class="rules-head"><div><p class="eyebrow">STORY</p><h2>当前故事覆盖</h2></div><button class="button accent" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存全部' }}</button></div><textarea v-model="storyJson" aria-label="故事规则 JSON" rows="14"></textarea></article><article><p class="eyebrow">PROMPT OPTIONS</p><h2>提示词偏好</h2><textarea v-model="promptJson" aria-label="提示词选项 JSON" rows="14"></textarea></article></div><article class="auto-card"><div><p class="eyebrow">AUTO CONFIGURATION</p><h2>自动配置</h2><p>输入当前目标，服务端会依据资料规模、用量和检索反馈给出可解释建议。</p></div><textarea v-model="autoGoal" rows="2" placeholder="例如：重点检查对白节奏与人物关系"></textarea><button class="button secondary" @click="runAutoConfig">重新计算</button><div class="auto-meta"><span>锁定字段：{{ listText(autoConfig.locked_fields) || '无' }}</span><span>原因：{{ listText(autoConfig.reasons) || '尚无变更' }}</span></div></article></template><p v-if="message" class="rules-message">{{ message }}</p></section>
</template>

<style scoped>
.rules-page { max-width: 1080px; margin: 0 auto; padding: 12px 0 60px; }.rules-page h1 { max-width: 760px; margin: 10px 0 16px; font-family: Georgia, serif; font-size: clamp(36px, 5vw, 62px); font-weight: 400; letter-spacing: -.055em; line-height: 1.08; }.rules-page h1 em { color: var(--accent); font-style: normal; }.intro { max-width: 620px; color: var(--muted); font-size: 13px; line-height: 1.8; }.rules-state { min-height: 220px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }.rules-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 34px; }.rules-grid article { padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }.rules-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }.rules-grid h2 { margin: 5px 0 15px; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.rules-grid textarea { width: 100%; padding: 12px; resize: vertical; border: 1px solid var(--line); border-radius: 9px; outline: 0; color: inherit; background: rgba(0,0,0,.1); font: 11px/1.6 ui-monospace, monospace; }.rules-grid small { display: block; margin-top: 8px; color: var(--muted); font-size: 10px; line-height: 1.6; }.rules-message { margin-top: 15px; color: #7da477; font-size: 12px; }.auto-card { display: grid; grid-template-columns: 1fr minmax(220px, .8fr) auto; align-items: end; gap: 14px; margin-top: 16px; padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }.auto-card h2 { margin: 5px 0 7px; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.auto-card p:not(.eyebrow) { margin: 0; color: var(--muted); font-size: 11px; line-height: 1.6; }.auto-card textarea { width: 100%; padding: 10px; resize: vertical; border: 1px solid var(--line); border-radius: 9px; color: inherit; background: transparent; font: inherit; font-size: 12px; }.auto-meta { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 11px; line-height: 1.6; }
@media (max-width: 720px) { .rules-grid { grid-template-columns: 1fr; } }
</style>
