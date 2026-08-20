<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'

const workspace = useWorkspaceStore()
const kind = ref<'character' | 'setting' | 'timeline'>('character')
const items = ref<any[]>([])
const loading = ref(false)
const error = ref('')

async function load() {
  if (!workspace.activeProjectId) return
  loading.value = true
  try { items.value = (await api.knowledgeEntities(workspace.activeProjectId, kind.value)).items || [] } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '实体视图读取失败' } finally { loading.value = false }
}

onMounted(load)
watch(kind, load)

function setKind(value: string) {
  if (value === 'setting' || value === 'timeline') kind.value = value
  else kind.value = 'character'
}
</script>

<template>
  <section class="entities-page"><p class="eyebrow">KNOWLEDGE PROJECTIONS</p><h1>把知识变成<em>可浏览的实体。</em></h1><p class="intro">角色卡、设定卡和时间线都是正式知识的实时投影；这里的浏览不会直接修改投影表。</p><div class="entity-tabs"><button v-for="tab in [{ value: 'character', label: '角色实体' }, { value: 'setting', label: '世界观实体' }, { value: 'timeline', label: '时间线' }]" :key="tab.value" :class="{ active: kind === tab.value }" @click="setKind(tab.value)">{{ tab.label }}</button></div><div v-if="loading" class="entity-state">正在整理实体…</div><div v-else-if="!items.length" class="entity-state">当前没有可投影的正式知识。</div><div v-else class="entity-grid"><article v-for="item in items" :key="item.id || item.event_id || item.name" class="entity-card"><p class="eyebrow">{{ item.entity_type || item.category || kind }}</p><h2>{{ item.name || item.title || item.summary || '未命名实体' }}</h2><p>{{ item.summary || item.description || item.chapter || item.time || '暂无摘要' }}</p><div v-if="item.aliases?.length" class="chips"><span v-for="alias in item.aliases.slice(0, 5)" :key="alias">{{ alias }}</span></div><small v-if="item.timeline?.length">关联事件 {{ item.timeline.length }} 条</small></article></div><p v-if="error" class="entity-error">{{ error }}</p></section>
</template>

<style scoped>
.entities-page { max-width: 1120px; margin: 0 auto; padding: 12px 0 60px; }.entities-page h1 { max-width: 760px; margin: 10px 0 16px; font-family: Georgia, serif; font-size: clamp(36px, 5vw, 62px); font-weight: 400; letter-spacing: -.055em; line-height: 1.08; }.entities-page h1 em { color: var(--accent); font-style: normal; }.intro { max-width: 650px; color: var(--muted); font-size: 13px; line-height: 1.8; }.entity-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin: 30px 0 18px; }.entity-tabs button { padding: 9px 13px; border: 1px solid var(--line); border-radius: 9px; color: var(--muted); background: transparent; cursor: pointer; font-size: 12px; }.entity-tabs button.active { border-color: var(--accent); color: var(--ink); background: rgba(191,118,89,.12); }.entity-state { min-height: 220px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }.entity-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }.entity-card { min-height: 150px; padding: 18px; border: 1px solid var(--line); border-radius: 14px; background: rgba(255,255,255,.05); }.entity-card h2 { margin: 6px 0 9px; font-family: Georgia, serif; font-size: 21px; font-weight: 400; }.entity-card p:not(.eyebrow) { color: var(--muted); font-size: 12px; line-height: 1.7; }.entity-card small { display: block; margin-top: 12px; color: var(--muted); font-size: 10px; }.chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 10px; }.chips span { padding: 3px 6px; border-radius: 99px; color: var(--accent); background: rgba(191,118,89,.13); font-size: 10px; }.entity-error { color: #d18d82; font-size: 12px; }
@media (max-width: 780px) { .entity-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } } @media (max-width: 520px) { .entity-grid { grid-template-columns: 1fr; } }
</style>
