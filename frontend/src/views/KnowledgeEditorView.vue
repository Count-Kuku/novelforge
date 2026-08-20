<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'

const route = useRoute()
const workspace = useWorkspaceStore()
const record = ref<Record<string, any>>({})
const fields = ref<any[]>([])
const values = ref<Record<string, string>>({})
const evidence = ref<any[]>([])
const revisions = ref<any[]>([])
const selectedRevisionId = ref('')
const revisionId = ref('')
const loading = ref(true)
const saving = ref(false)
const message = ref('')
const selectedRevision = computed(() => revisions.value.find((item) => String(item.revision_id) === selectedRevisionId.value) || null)

function stringify(value: unknown, kind: string) {
  return kind === 'list' && Array.isArray(value) ? value.join('\n') : String(value ?? '')
}

async function load() {
  if (!workspace.activeProjectId) return
  const type = String(route.params.recordType || 'knowledge')
  const id = String(route.params.recordId || '')
  try {
    record.value = await api.knowledgeDetail(workspace.activeProjectId, type, id)
    const category = String(record.value.category || record.value.payload?.category || 'characters')
    fields.value = (await api.knowledgeSchema(category)).fields
    const payload = (record.value.payload && typeof record.value.payload === 'object' ? record.value.payload : record.value) as Record<string, any>
    for (const field of fields.value) values.value[field.key] = stringify(payload.typed_data?.[field.key] ?? payload[field.key], field.kind)
    revisions.value = (await api.knowledgeRevisions(workspace.activeProjectId, type, id)).revisions || []
    revisionId.value = String(revisions.value[0]?.revision_id || '')
    selectedRevisionId.value = String(revisions.value[1]?.revision_id || revisions.value[0]?.revision_id || '')
    evidence.value = (await api.knowledgeEvidence(workspace.activeProjectId, type, id)).evidence || []
  } catch (reason) { message.value = reason instanceof ApiClientError ? reason.message : '知识编辑器读取失败' } finally { loading.value = false }
}

function applyRevisionSnapshot() {
  const snapshot = selectedRevision.value?.snapshot
  if (!snapshot || typeof snapshot !== 'object') return
  const typed = (snapshot.typed_data && typeof snapshot.typed_data === 'object' ? snapshot.typed_data : snapshot) as Record<string, unknown>
  for (const field of fields.value) values.value[field.key] = stringify(typed[field.key], field.kind)
  message.value = '历史快照已载入编辑区；保存前可继续手动合并。'
}

async function save() {
  if (!workspace.activeProjectId || saving.value) return
  saving.value = true
  const typedData: Record<string, unknown> = {}
  const patch: Record<string, unknown> = { typed_data: typedData }
  for (const field of fields.value) typedData[field.key] = field.kind === 'list' ? values.value[field.key].split(/\r?\n|、|；/).map((item) => item.trim()).filter(Boolean) : values.value[field.key]
  try { const result = await api.updateKnowledge(workspace.activeProjectId, String(route.params.recordType || 'knowledge'), String(route.params.recordId || ''), patch, 'Vue 类型化编辑', revisionId.value || undefined); record.value = result.record; message.value = '类型化知识修订已保存'; await load() } catch (reason) { message.value = reason instanceof ApiClientError && reason.status === 409 ? '条目已被修改，请重新加载后合并。' : reason instanceof Error ? reason.message : '保存失败' } finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <section class="knowledge-editor-page"><p class="eyebrow">TYPED KNOWLEDGE EDITOR</p><h1>编辑一条<em>可验证的知识。</em></h1><div v-if="loading" class="editor-state">正在读取知识条目…</div><template v-else><div class="editor-grid"><article class="typed-form"><div v-for="field in fields" :key="field.key" class="field"><label>{{ field.label }}<small v-if="field.required">必填</small></label><textarea v-model="values[field.key]" :rows="field.kind === 'list' ? 3 : 2" :aria-label="field.label"></textarea></div><button class="button accent" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存类型化修订' }}</button></article><aside class="evidence-card"><p class="eyebrow">EVIDENCE</p><h2>证据与来源</h2><div v-if="!evidence.length" class="editor-state small">暂无可展示证据。</div><div v-for="item in evidence" :key="item.evidence_id || item.id" class="evidence-row"><strong>{{ item.source_title || '来源' }}</strong><p><mark>{{ item.quote || item.excerpt || item.content || '无摘录' }}</mark></p><small>{{ item.validation_status || '待验证' }} · {{ item.evidence_strength || '普通证据' }}</small></div></aside></div><article class="revision-card"><div class="revision-heading"><div><p class="eyebrow">REVISION TIMELINE</p><h2>当前与历史快照</h2></div><button class="button secondary" :disabled="!selectedRevision" @click="applyRevisionSnapshot">载入所选快照并手动合并</button></div><div v-if="!revisions.length" class="editor-state small">暂无修订历史。</div><div v-else class="revision-list"><label v-for="item in revisions" :key="item.revision_id" class="revision-row"><input v-model="selectedRevisionId" type="radio" name="knowledge-revision" :value="String(item.revision_id)" /><span><strong>修订 #{{ item.revision_no }}</strong><small>{{ item.change_type || 'update' }} · {{ item.reason || '无说明' }} · {{ item.created_at || '' }}</small></span></label></div></article></template><p v-if="message" class="editor-message">{{ message }}</p></section>
</template>

<style scoped>
.knowledge-editor-page { max-width: 1080px; margin: 0 auto; padding: 12px 0 60px; }.knowledge-editor-page h1 { margin: 10px 0 28px; font-family: Georgia, serif; font-size: clamp(36px, 5vw, 60px); font-weight: 400; letter-spacing: -.055em; }.knowledge-editor-page h1 em { color: var(--accent); font-style: normal; }.editor-grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(260px, .8fr); gap: 16px; }.typed-form, .evidence-card { padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }.field { display: grid; gap: 6px; margin-bottom: 15px; }.field label { color: var(--ink); font-size: 12px; }.field label small { margin-left: 7px; color: var(--accent); font-size: 10px; }.field textarea { width: 100%; padding: 10px; resize: vertical; border: 1px solid var(--line); border-radius: 8px; color: inherit; background: transparent; font: 12px/1.6 inherit; }.evidence-card h2 { margin: 5px 0 15px; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.evidence-row { padding: 10px 0; border-top: 1px solid var(--line); }.evidence-row strong { display: block; font-size: 11px; }.evidence-row p { margin: 5px 0 0; color: var(--muted); font-size: 11px; line-height: 1.6; }.editor-state { min-height: 200px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }.editor-state.small { min-height: 80px; }.editor-message { margin-top: 12px; color: #7da477; font-size: 12px; }
.evidence-row small { display: block; margin-top: 6px; color: var(--muted); font-size: 10px; }.evidence-row mark { color: inherit; background: rgba(225, 170, 104, .18); }.revision-card { margin-top: 16px; padding: 20px 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.04); }.revision-heading { display: flex; align-items: start; justify-content: space-between; gap: 12px; }.revision-card h2 { margin: 4px 0 0; font-family: Georgia, serif; font-size: 23px; font-weight: 400; }.revision-list { margin-top: 13px; border-top: 1px solid var(--line); }.revision-row { display: flex; align-items: flex-start; gap: 9px; padding: 11px 0; border-bottom: 1px solid var(--line); cursor: pointer; }.revision-row span { display: grid; gap: 3px; }.revision-row strong { font-size: 12px; font-weight: 500; }.revision-row small { color: var(--muted); font-size: 10px; }
@media (max-width: 760px) { .editor-grid { grid-template-columns: 1fr; } }
.field textarea { font: inherit; font-size: 12px; line-height: 1.6; }
</style>
