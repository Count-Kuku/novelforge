<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'
import { dialog } from '../ui/dialog'

type RuleScope = 'all' | 'outline' | 'chapter_outline' | 'write' | 'review' | 'setting_extraction'
type RuleLayer = 'global' | 'project' | 'story'

const workspace = useWorkspaceStore()
const ruleScopes: { key: RuleScope; label: string; hint: string }[] = [
  { key: 'all', label: '通用规则', hint: '适用于全部生成与分析任务' },
  { key: 'outline', label: '全书大纲', hint: '用于全书结构和主线规划' },
  { key: 'chapter_outline', label: '章节细纲', hint: '用于章节目标、冲突和节奏规划' },
  { key: 'write', label: '正文写作', hint: '用于正文生成和改写' },
  { key: 'review', label: '章节审阅', hint: '用于审阅、评价和修改建议' },
  { key: 'setting_extraction', label: '设定提炼', hint: '用于从资料和正文中提取知识' },
]
const layerTabs: { key: RuleLayer; label: string; hint: string }[] = [
  { key: 'global', label: '全局', hint: '所有项目默认使用' },
  { key: 'project', label: '项目', hint: '当前项目中的全部故事使用' },
  { key: 'story', label: '故事', hint: '仅当前故事使用' },
]
const capabilityOptions = [
  { value: 'outline', label: '全书大纲' },
  { value: 'chapter_outline', label: '章节细纲' },
  { value: 'write', label: '正文写作' },
  { value: 'review', label: '章节审阅' },
  { value: 'setting_extraction', label: '设定提炼' },
]

const activeLayer = ref<RuleLayer>('story')
const ruleDrafts = ref<Record<RuleLayer, Record<RuleScope, string>>>(emptyRuleDrafts())
const promptOptions = ref<Record<string, any>[]>([])
const autoConfig = ref<Record<string, any>>({})
const autoGoal = ref('')
const loading = ref(true)
const saving = ref(false)
const configuring = ref(false)
const message = ref('')
const messageTone = ref<'success' | 'error'>('success')

function emptyRuleDrafts(): Record<RuleLayer, Record<RuleScope, string>> {
  const layer = () => Object.fromEntries(ruleScopes.map((scope) => [scope.key, ''])) as Record<RuleScope, string>
  return { global: layer(), project: layer(), story: layer() }
}

function fillLayer(layer: RuleLayer, rules: unknown) {
  const source = rules && typeof rules === 'object' ? rules as Record<string, unknown> : {}
  for (const scope of ruleScopes) {
    const values = Array.isArray(source[scope.key]) ? source[scope.key] as unknown[] : []
    ruleDrafts.value[layer][scope.key] = values.map((item) => String(item)).join('\n')
  }
}

function serializeLayer(layer: RuleLayer) {
  return Object.fromEntries(ruleScopes.map((scope) => [
    scope.key,
    ruleDrafts.value[layer][scope.key].split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
  ]))
}

function listText(value: unknown): string {
  return Array.isArray(value) ? value.map((item) => String(item)).join('、') : ''
}

async function load() {
  if (!workspace.activeProjectId || !workspace.activeStory) { loading.value = false; return }
  loading.value = true
  message.value = ''
  try {
    const [data, layers, options, auto] = await Promise.all([
      api.rules(workspace.activeProjectId, workspace.activeStory.story_id),
      api.settingsRules(workspace.activeProjectId, workspace.activeStory.story_id),
      api.promptOptions('story', workspace.activeProjectId, workspace.activeStory.story_id),
      api.autoConfiguration('chapter_write', workspace.activeProjectId, workspace.activeStory.story_id),
    ])
    fillLayer('global', layers.global || {})
    fillLayer('project', layers.project || data.project || {})
    fillLayer('story', data.story || layers.story || {})
    promptOptions.value = (options.options || []).map((item) => ({ ...item }))
    autoConfig.value = auto.state || {}
  } catch (reason) {
    message.value = reason instanceof ApiClientError ? reason.message : '无法读取规则与偏好'
    messageTone.value = 'error'
  } finally { loading.value = false }
}

async function save() {
  if (!workspace.activeProjectId || !workspace.activeStory || saving.value) return
  saving.value = true
  message.value = ''
  try {
    await api.updateSettingsRules('global', serializeLayer('global'), workspace.activeProjectId, workspace.activeStory.story_id)
    await api.updateSettingsRules('project', serializeLayer('project'), workspace.activeProjectId, workspace.activeStory.story_id)
    await api.updateRules(workspace.activeProjectId, workspace.activeStory.story_id, serializeLayer('story'))
    await api.updatePromptOptions('story', promptOptions.value, workspace.activeProjectId, workspace.activeStory.story_id)
    message.value = '规则与提示词选项已保存'
    messageTone.value = 'success'
  } catch (reason) {
    message.value = reason instanceof Error ? reason.message : '保存失败'
    messageTone.value = 'error'
  } finally { saving.value = false }
}

function addPromptOption() {
  promptOptions.value = [
    ...promptOptions.value,
    {
      id: `story_custom_${Date.now()}`,
      name: '新提示词选项',
      capability: 'write',
      category: 'custom',
      slot: 'custom',
      priority: 50,
      enabled: true,
      content: '',
      tags: [],
    },
  ]
}

async function removePromptOption(index: number) {
  const option = promptOptions.value[index]
  if (!await dialog.confirm({ title: '删除提示词选项？', message: `“${option?.name || '未命名选项'}”将在保存后删除。`, confirmLabel: '删除', tone: 'danger' })) return
  promptOptions.value = promptOptions.value.filter((_, itemIndex) => itemIndex !== index)
}

async function runAutoConfig() {
  if (!workspace.activeProjectId || !workspace.activeStory || configuring.value) return
  configuring.value = true
  try {
    autoConfig.value = await api.configureAutoConfiguration('chapter_write', { goal: autoGoal.value }, workspace.activeProjectId, workspace.activeStory.story_id)
    message.value = '自动配置已更新'
    messageTone.value = 'success'
  } catch (reason) {
    message.value = reason instanceof Error ? reason.message : '自动配置失败'
    messageTone.value = 'error'
  } finally { configuring.value = false }
}

onMounted(load)
</script>

<template>
  <section class="rules-page">
    <div class="page-heading"><div><p class="eyebrow">规则与偏好</p><h1>配置生成规则和<em>提示词选项</em></h1><p class="intro">每行填写一条规则。故事规则优先于项目规则，项目规则优先于全局规则。</p></div><button class="button accent" :disabled="saving || loading" @click="save">{{ saving ? '保存中…' : '保存全部' }}</button></div>
    <div v-if="loading" class="rules-state">正在读取规则…</div>
    <template v-else>
      <nav class="layer-tabs" aria-label="规则层级"><button v-for="layer in layerTabs" :key="layer.key" :class="{ active: activeLayer === layer.key }" @click="activeLayer = layer.key"><strong>{{ layer.label }}</strong><small>{{ layer.hint }}</small></button></nav>
      <div class="rule-grid"><label v-for="scope in ruleScopes" :key="scope.key" class="rule-card"><span><strong>{{ scope.label }}</strong><small>{{ scope.hint }}</small></span><textarea v-model="ruleDrafts[activeLayer][scope.key]" rows="5" :aria-label="`${layerTabs.find((item) => item.key === activeLayer)?.label}${scope.label}`" placeholder="每行一条规则"></textarea></label></div>

      <article class="prompt-panel">
        <div class="section-heading"><div><p class="eyebrow">当前故事</p><h2>提示词选项</h2><p>用于补充特定任务的规划方法、文风或审阅标准。</p></div><button class="button secondary" @click="addPromptOption">新增选项</button></div>
        <div v-if="!promptOptions.length" class="empty-state">当前故事没有自定义提示词选项。</div>
        <div v-else class="prompt-list"><article v-for="(option, index) in promptOptions" :key="option.id || index" class="prompt-card"><div class="prompt-card-head"><input v-model="option.name" aria-label="选项名称" placeholder="选项名称" /><label><input v-model="option.enabled" type="checkbox" />启用</label><button class="remove-option" @click="removePromptOption(index)">删除</button></div><div class="prompt-meta"><label>适用任务<select v-model="option.capability"><option v-for="capability in capabilityOptions" :key="capability.value" :value="capability.value">{{ capability.label }}</option></select></label><label>优先级<input v-model.number="option.priority" type="number" min="0" max="100" /></label></div><textarea v-model="option.content" rows="4" aria-label="提示词选项内容" placeholder="填写具体要求"></textarea></article></div>
      </article>

      <article class="auto-card"><div><p class="eyebrow">自动配置</p><h2>按写作目标调整</h2><p>根据资料规模、历史用量和检索反馈计算建议，不会修改用户锁定的字段。</p></div><textarea v-model="autoGoal" rows="2" placeholder="例如：重点检查对白节奏与人物关系"></textarea><button class="button secondary" :disabled="configuring" @click="runAutoConfig">{{ configuring ? '计算中…' : '重新计算' }}</button><div class="auto-meta"><span>锁定字段：{{ listText(autoConfig.locked_fields) || '无' }}</span><span>调整原因：{{ listText(autoConfig.reasons) || '暂无调整' }}</span></div></article>
    </template>
    <p v-if="message" class="rules-message" :class="messageTone" role="status">{{ message }}</p>
  </section>
</template>

<style scoped>
.rules-page { max-width: 1120px; margin: 0 auto; padding: 12px 0 60px; }
.page-heading { display: flex; align-items: end; justify-content: space-between; gap: 24px; }
.rules-page h1 { max-width: 780px; margin: 10px 0 16px; font-family: Georgia, serif; font-size: clamp(36px, 5vw, 62px); font-weight: 400; letter-spacing: -.055em; line-height: 1.08; }
.rules-page h1 em { color: var(--accent); font-style: normal; }
.intro { max-width: 660px; color: var(--muted); font-size: 13px; line-height: 1.8; }
.rules-state, .empty-state { min-height: 180px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }
.layer-tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; margin-top: 34px; }
.layer-tabs button { display: grid; gap: 4px; padding: 13px 15px; border: 1px solid var(--line); border-radius: 11px; color: var(--muted); background: transparent; text-align: left; }
.layer-tabs button.active { color: var(--ink); border-color: rgba(169,75,47,.4); background: rgba(169,75,47,.08); }
.layer-tabs strong { font-size: 13px; }.layer-tabs small { font-size: 10px; }
.rule-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 14px; }
.rule-card { display: grid; gap: 12px; padding: 19px; border: 1px solid var(--line); border-radius: 14px; background: rgba(255,255,255,.05); }
.rule-card > span { display: grid; gap: 4px; }.rule-card strong { font-family: Georgia, serif; font-size: 18px; font-weight: 500; }.rule-card small { color: var(--muted); font-size: 10px; }
.rule-card textarea, .prompt-card textarea, .auto-card textarea { width: 100%; padding: 11px 12px; resize: vertical; border: 1px solid var(--line); border-radius: 9px; outline: 0; color: inherit; background: rgba(255,255,255,.04); font-size: 12px; line-height: 1.65; }
.prompt-panel { margin-top: 18px; padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }
.section-heading { display: flex; align-items: start; justify-content: space-between; gap: 16px; }.section-heading h2, .auto-card h2 { margin: 4px 0 6px; font-family: Georgia, serif; font-size: 25px; font-weight: 400; }.section-heading p:not(.eyebrow), .auto-card p:not(.eyebrow) { margin: 0; color: var(--muted); font-size: 11px; line-height: 1.6; }
.prompt-list { display: grid; gap: 10px; margin-top: 18px; }.prompt-card { padding: 16px; border: 1px solid var(--line); border-radius: 12px; background: rgba(255,255,255,.04); }
.prompt-card-head { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 12px; }.prompt-card-head > input { padding: 7px 0; border: 0; border-bottom: 1px solid var(--line); outline: 0; color: inherit; background: transparent; font-family: Georgia, serif; font-size: 17px; }.prompt-card-head label { color: var(--muted); font-size: 11px; }.remove-option { padding: 5px 7px; border: 0; color: #b55f46; background: transparent; font-size: 10px; }
.prompt-meta { display: flex; gap: 12px; margin: 12px 0; }.prompt-meta label { display: grid; gap: 5px; color: var(--muted); font-size: 10px; }.prompt-meta select, .prompt-meta input { padding: 7px 8px; border: 1px solid var(--line); border-radius: 7px; color: inherit; background: transparent; font-size: 11px; }
.auto-card { display: grid; grid-template-columns: 1fr minmax(220px, .8fr) auto; align-items: end; gap: 14px; margin-top: 18px; padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }.auto-meta { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 11px; }
.rules-message { margin-top: 15px; font-size: 12px; }.rules-message.success { color: #67805f; }.rules-message.error { color: #b55f46; }
@media (max-width: 760px) { .page-heading { align-items: flex-start; flex-direction: column; }.layer-tabs, .rule-grid { grid-template-columns: 1fr; }.auto-card { grid-template-columns: 1fr; }.auto-meta { grid-column: auto; } }
</style>
