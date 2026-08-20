<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'
import { api } from '../api/client'

const workspace = useWorkspaceStore()
const capabilities = ref<Record<string, { available: boolean; status: string; message: string; provider?: string }>>({})
const loading = ref(true)
const error = ref('')
const profiles = ref<Record<string, any>[]>([])
const activeProfileId = ref('')
const selectedProfileId = ref('')
const modelName = ref('')
const baseUrl = ref('')
const providerType = ref('auto')
const apiKey = ref('')
const embeddingMode = ref('disabled')
const embeddingModelName = ref('')
const savingProfile = ref(false)
const profileMessage = ref('')
const usage = ref<{ today: Record<string, any>; month: Record<string, any> } | null>(null)
const breakdownDimension = ref<'project' | 'story' | 'model' | 'operation' | 'agent'>('operation')
const breakdownRows = ref<Record<string, any>[]>([])
const breakdownLoading = ref(false)

function selectProfile(profile: Record<string, any>) {
  selectedProfileId.value = String(profile.id || '')
  modelName.value = String(profile.model_name || '')
  baseUrl.value = String(profile.base_url || '')
  providerType.value = String(profile.provider_type || 'auto')
  embeddingMode.value = String(profile.embedding_mode || 'disabled')
  embeddingModelName.value = String(profile.embedding_model_name || '')
  apiKey.value = ''
}

async function saveProfile() {
  if (!selectedProfileId.value || savingProfile.value) return
  savingProfile.value = true
  profileMessage.value = ''
  try {
    const result = await api.updateModelProfile({ profile_id: selectedProfileId.value, name: profiles.value.find((item) => item.id === selectedProfileId.value)?.name || '默认模型', provider_type: providerType.value, base_url: baseUrl.value, model_name: modelName.value, embedding_mode: embeddingMode.value, embedding_model_name: embeddingModelName.value, api_key: apiKey.value })
    profileMessage.value = result.saved ? '模型配置已保存（密钥仅写入系统凭据存储）' : '配置未变更'
    const data = await api.modelProfiles(); profiles.value = data.profiles; activeProfileId.value = data.active_profile_id
  } catch (reason) { profileMessage.value = reason instanceof Error ? reason.message : '保存模型配置失败' } finally { savingProfile.value = false }
}

async function activateProfile() {
  if (!selectedProfileId.value || selectedProfileId.value === activeProfileId.value) return
  try { await api.activateModelProfile(selectedProfileId.value); activeProfileId.value = selectedProfileId.value; profileMessage.value = '已切换活动模型' } catch (reason) { profileMessage.value = reason instanceof Error ? reason.message : '切换模型失败' }
}

async function loadBreakdown() {
  breakdownLoading.value = true
  try {
    const data = await api.usageBreakdown(breakdownDimension.value, workspace.activeProjectId || undefined, workspace.activeStory?.story_id)
    breakdownRows.value = data.rows as Record<string, any>[]
  } catch (reason) {
    breakdownRows.value = []
    error.value = reason instanceof Error ? reason.message : '用量明细读取失败'
  } finally { breakdownLoading.value = false }
}

onMounted(async () => {
  try { capabilities.value = (await api.capabilities()).capabilities; const data = await api.modelProfiles(); profiles.value = data.profiles; activeProfileId.value = data.active_profile_id; if (profiles.value[0]) selectProfile(profiles.value.find((item) => item.id === activeProfileId.value) || profiles.value[0]); usage.value = await api.usage(workspace.activeProjectId || undefined, workspace.activeStory?.story_id); await loadBreakdown() } catch (reason) { error.value = reason instanceof Error ? reason.message : '无法读取能力状态' } finally { loading.value = false }
})
</script>

<template>
  <article v-if="usage" class="usage-panel"><div><p class="eyebrow">模型用量</p><strong>今日 {{ usage.today.request_count || 0 }} 次请求 · {{ usage.today.total_tokens || 0 }} tokens</strong><small>本月 {{ usage.month.request_count || 0 }} 次 · 约 ${{ Number(usage.month.cost_usd || 0).toFixed(4) }}；{{ usage.month.cost_complete ? '价格完整' : '含估算或未计价调用' }}</small></div><span class="usage-cost">今日约 ${{ Number(usage.today.cost_usd || 0).toFixed(4) }}</span></article>
  <article v-if="usage" class="usage-breakdown"><div class="usage-breakdown-heading"><div><p class="eyebrow">用量明细</p><h2>按维度查看</h2></div><select v-model="breakdownDimension" aria-label="用量维度" @change="loadBreakdown"><option value="operation">操作</option><option value="model">模型</option><option value="story">故事</option><option value="project">项目</option><option value="agent">Agent</option></select></div><div v-if="breakdownLoading" class="breakdown-state">正在读取明细…</div><div v-else-if="!breakdownRows.length" class="breakdown-state">当前维度暂无记录。</div><div v-else class="breakdown-table" role="table" aria-label="用量明细"><div class="breakdown-row header" role="row"><span>维度</span><span>请求 / tokens</span><span>费用</span></div><div v-for="row in breakdownRows" :key="String(row.bucket)" class="breakdown-row" role="row"><strong>{{ row.bucket || '未标记' }}</strong><span>{{ row.request_count || 0 }} 次 · {{ row.total_tokens || 0 }} tokens</span><span>${{ Number(row.cost_usd || 0).toFixed(4) }}</span></div></div></article>
  <section class="settings-page"><p class="eyebrow">模型与能力</p><h1>配置模型、检索与<em>本地能力</em></h1><p class="intro">查看聊天、Embedding、搜索和 OCR 的可用状态，并管理模型连接。已保存的密钥不会在页面中回显。</p><div v-if="loading" class="settings-state">正在检查本地能力…</div><template v-else><div class="capability-grid"><article v-for="(item, key) in capabilities" :key="key" class="capability-card"><div class="status-dot" :class="{ ready: item.available }"></div><div><strong>{{ key }}</strong><small>{{ item.provider || '本地服务' }}</small><p>{{ item.available ? '当前可用' : (item.message || item.status) }}</p></div></article></div><article v-if="profiles.length" class="model-panel"><div class="model-panel-heading"><div><p class="eyebrow">模型方案</p><h2>模型与凭据</h2></div><span v-if="profileMessage" class="saved-state">{{ profileMessage }}</span></div><div class="profile-tabs"><button v-for="profile in profiles" :key="profile.id" :class="{ active: selectedProfileId === profile.id }" @click="selectProfile(profile)">{{ profile.name || profile.id }}<small>{{ activeProfileId === profile.id ? '当前使用' : '可切换' }}</small></button></div><div class="model-form"><label>Provider 类型<input v-model="providerType" /></label><label>Base URL<input v-model="baseUrl" placeholder="https://…" /></label><label>模型名称<input v-model="modelName" /></label><label>Embedding 模式<select v-model="embeddingMode"><option value="disabled">关闭</option><option value="openai_compatible">兼容 API</option></select></label><label>Embedding 模型<input v-model="embeddingModelName" /></label><label>API Key（留空保持不变）<input v-model="apiKey" type="password" autocomplete="new-password" placeholder="不会回显已存密钥" /></label></div><div class="model-actions"><button class="button secondary" :disabled="savingProfile" @click="saveProfile">{{ savingProfile ? '保存中…' : '保存模型配置' }}</button><button class="button accent" :disabled="selectedProfileId === activeProfileId" @click="activateProfile">设为当前模型</button></div></article></template><div class="settings-note"><strong>当前故事</strong><span>{{ workspace.activeStory?.name || '未选择故事' }} · {{ workspace.mode === 'conversational' ? '对话模式' : '规划模式' }}</span></div><p v-if="error" class="settings-error">{{ error }}</p></section>
</template>

<style scoped>
.settings-page { max-width: 940px; margin: 0 auto; padding: 12px 0 60px; }.settings-page h1 { max-width: 650px; margin: 12px 0 18px; font-family: Georgia, serif; font-size: clamp(37px, 5vw, 62px); font-weight: 400; letter-spacing: -.055em; line-height: 1.08; }.settings-page h1 em { color: var(--accent, #b86c4d); font-style: normal; }.intro { max-width: 580px; color: var(--muted, #8b8175); font-size: 14px; line-height: 1.8; }.settings-state { min-height: 180px; display: grid; place-items: center; color: var(--muted, #8b8175); font-size: 13px; }.capability-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 40px; }.capability-card { display: flex; gap: 13px; padding: 20px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 15px; background: rgba(255,255,255,.06); }.status-dot { flex: 0 0 8px; width: 8px; height: 8px; margin-top: 5px; border-radius: 50%; background: #b66d58; }.status-dot.ready { background: #7da477; }.capability-card strong { display: block; font-family: Georgia, serif; font-size: 19px; font-weight: 400; }.capability-card small { display: block; margin-top: 3px; color: var(--muted, #8b8175); font-size: 10px; }.capability-card p { margin: 11px 0 0; color: var(--muted, #8b8175); font-size: 12px; line-height: 1.6; }.settings-note { display: flex; justify-content: space-between; gap: 20px; margin-top: 22px; padding: 17px 20px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 12px; color: var(--muted, #8b8175); font-size: 12px; }.settings-note strong { color: inherit; font-family: Georgia, serif; font-size: 16px; font-weight: 400; }.settings-error { color: #c67862; font-size: 12px; }
.usage-panel { max-width: 940px; margin: 0 auto 18px; padding: 17px 20px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 12px; color: var(--muted, #8b8175); background: rgba(255,255,255,.04); }.usage-panel strong { display: block; margin-top: 5px; color: var(--ink, #eee6dc); font-size: 13px; font-weight: 500; }.usage-panel small { display: block; margin-top: 5px; font-size: 10px; }.usage-cost { color: var(--accent, #b86c4d); font-size: 12px; }
.usage-breakdown { max-width: 940px; margin: 0 auto 22px; padding: 18px 20px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 12px; background: rgba(255,255,255,.035); }.usage-breakdown-heading { display: flex; align-items: start; justify-content: space-between; gap: 12px; }.usage-breakdown h2 { margin: 4px 0 0; font-family: Georgia, serif; font-size: 22px; font-weight: 400; }.usage-breakdown select { min-width: 110px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; color: inherit; background: transparent; font-size: 11px; }.breakdown-table { margin-top: 14px; border-top: 1px solid var(--line); }.breakdown-row { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) 110px; gap: 12px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--line); color: var(--muted); font-size: 11px; }.breakdown-row strong { color: var(--ink); font-size: 12px; font-weight: 500; }.breakdown-row.header { color: var(--muted); font-size: 10px; text-transform: uppercase; }.breakdown-state { min-height: 60px; display: grid; place-items: center; color: var(--muted); font-size: 11px; }
.model-panel { margin-top: 22px; padding: 24px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 16px; background: rgba(255,255,255,.05); }.model-panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 15px; }.model-panel h2 { margin: 5px 0 0; font-family: Georgia, serif; font-size: 25px; font-weight: 400; }.saved-state { color: #7da477; font-size: 11px; }.profile-tabs { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 20px; }.profile-tabs button { display: grid; gap: 3px; padding: 9px 12px; border: 1px solid var(--line); border-radius: 9px; color: var(--muted); background: transparent; cursor: pointer; font-size: 12px; text-align: left; }.profile-tabs button.active { border-color: #c88468; color: var(--ink); background: rgba(200,132,104,.12); }.profile-tabs small { color: var(--muted); font-size: 10px; }.model-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }.model-form label { display: grid; gap: 6px; color: var(--muted); font-size: 11px; }.model-form input, .model-form select { width: 100%; padding: 9px 10px; border: 1px solid var(--line); border-radius: 8px; outline: 0; color: inherit; background: transparent; font-size: 12px; }.model-actions { display: flex; gap: 8px; margin-top: 16px; }
@media (max-width: 680px) { .capability-grid, .model-form { grid-template-columns: 1fr; }.settings-note { align-items: flex-start; flex-direction: column; } }
</style>
