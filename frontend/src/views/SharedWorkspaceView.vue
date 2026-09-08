<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'
import { dialog } from '../ui/dialog'
import { notify } from '../ui/notifications'

const workspace = useWorkspaceStore()
const route = useRoute()
const router = useRouter()
const summary = ref<Record<string, unknown>>({})
const query = ref('')
const results = ref<any[]>([])
const nextCursor = ref('')
const recordTypeFilter = ref('')
const loadingMore = ref(false)
const loading = ref(true)
const searching = ref(false)
const error = ref('')
const tasks = ref<{ ingestion: any[] }>({ ingestion: [] })
const capabilities = ref<Record<string, { available: boolean; status: string; message: string; provider?: string }>>({})
const selectedDetail = ref<Record<string, unknown> | null>(null)
const detailLoading = ref(false)
const pending = ref<any[]>([])
const pendingBusy = ref(false)
const pendingResolution = ref<Record<string, string>>({})
const resolvingPendingId = ref('')
const detailJson = ref('')
const detailRecordType = ref('knowledge')
const detailRecordId = ref('')
const detailSaving = ref(false)
const detailRevisions = ref<any[]>([])
const revisionDiff = ref('')
const detailEvidence = ref<any[]>([])
const detailOwner = ref<{ projectId: string; storyId: string; branchId?: string }>({ projectId: '', storyId: '' })
const copyingStory = ref(false)
const developerMode = ref(false)
watch(developerMode, (enabled) => document.documentElement.classList.toggle('novelforge-developer', enabled))
const resultScrollTop = ref(0)
const resultViewport = ref<HTMLElement | null>(null)
const resultRowHeight = 96
const resultWindow = 12
const resultStart = computed(() => Math.max(0, Math.floor(resultScrollTop.value / resultRowHeight) - 2))
const visibleResults = computed(() => results.value.slice(resultStart.value, resultStart.value + resultWindow + 4))
const resultTopSpacer = computed(() => resultStart.value * resultRowHeight)
const resultBottomSpacer = computed(() => Math.max(0, (results.value.length - resultStart.value - visibleResults.value.length) * resultRowHeight))
const selectedKnowledgeIds = ref<string[]>([])
const promoting = ref(false)
let pendingRequest = 0
let searchRequest = 0
let detailRequest = 0

function scopeKey(projectId = workspace.activeProjectId, storyId = workspace.activeStory?.story_id || '', branchId = workspace.activeBranchId || '') {
  return `${projectId}:${storyId}:${branchId}`
}

function currentScopeKey() {
  return scopeKey()
}

function pendingNeedsEntityResolution(item: any): boolean {
  return String(item?.entity_resolution_status || '').trim().toLowerCase() === 'pending_confirmation'
}

function pendingResolutionOptions(item: any): any[] {
  return Array.isArray(item?.entity_resolution_options) ? item.entity_resolution_options : []
}

function pendingResolutionLabel(option: any): string {
  const name = String(option?.canonical_name || '未命名实体')
  const isNew = Boolean(option?.is_new || option?.create_new)
  const source = String(option?.source_title || option?.worldline_label || option?.worldline_id || '').trim()
  const aliases = Array.isArray(option?.aliases) ? option.aliases.map((alias: unknown) => String(alias)).filter(Boolean).slice(0, 2) : []
  return [name, isNew ? '当前故事/世界线 · 创建新实体' : source ? `来源 ${source}` : '', aliases.length ? `又名 ${aliases.join('、')}` : ''].filter(Boolean).join(' · ')
}

function pendingResolutionTarget(item: any): string {
  return pendingResolution.value[String(item?.pending_id || '')] || ''
}

function pendingResolutionPrompt(item: any): string {
  const reason = String(item?.entity_resolution_reason || '').trim()
  if (reason) return reason
  const endpoint = String(item?.entity_resolution_endpoint || '').toLowerCase()
  if (endpoint === 'source') return '关系起点的来源不唯一，请先选择世界线/实体'
  if (endpoint === 'target') return '关系终点的来源不唯一，请先选择世界线/实体'
  return '检测到多个同名实体，请先选择对应世界线'
}

async function reloadPending() {
  const projectId = workspace.activeProjectId
  const storyId = workspace.activeStory?.story_id || ''
  const branchId = workspace.activeBranchId || undefined
  const request = ++pendingRequest
  if (!projectId || !storyId) {
    pending.value = []
    return
  }
  try {
    const data = await api.pendingKnowledge(projectId, storyId, branchId)
    if (request !== pendingRequest || projectId !== workspace.activeProjectId || storyId !== workspace.activeStory?.story_id || branchId !== (workspace.activeBranchId || undefined)) return
    pending.value = data.items || []
  } catch (reason) {
    if (request !== pendingRequest) return
    error.value = reason instanceof ApiClientError ? reason.message : '当前世界线知识加载失败'
  }
}

watch(() => [workspace.activeProjectId, workspace.activeStoryId, workspace.activeBranchId], async () => {
  searchRequest += 1
  detailRequest += 1
  searching.value = false
  loadingMore.value = false
  detailLoading.value = false
  detailSaving.value = false
  selectedKnowledgeIds.value = []
  results.value = []
  selectedDetail.value = null
  detailRecordId.value = ''
  detailRecordType.value = 'knowledge'
  detailJson.value = ''
  detailRevisions.value = []
  detailEvidence.value = []
  detailOwner.value = { projectId: '', storyId: '' }
  pendingResolution.value = {}
  if (!workspace.activeProjectId || !workspace.activeStory) return
  await reloadPending()
  if (query.value.trim()) await search()
})

function onResultScroll(event: Event) {
  resultScrollTop.value = (event.currentTarget as HTMLElement).scrollTop
}

function capabilityLabel(key: string) {
  return ({ chat: '文本生成', embedding: '语义检索', search: '网络搜索', ocr: '文字识别' } as Record<string, string>)[key.toLowerCase()] || key
}

onMounted(async () => {
  query.value = String(route.query.q || '')
  recordTypeFilter.value = String(route.query.type || '')
  if (!workspace.activeProjectId || !workspace.activeStory) { loading.value = false; return }
  try {
    summary.value = await api.summary(workspace.activeProjectId, workspace.activeStory.story_id)
    const [taskData, capabilityData, developerData] = await Promise.all([
      api.tasks(workspace.activeProjectId),
      api.capabilities(),
      api.developerSettings(),
    ])
    tasks.value = { ingestion: taskData.ingestion || [] }
    capabilities.value = capabilityData.capabilities
    developerMode.value = Boolean(developerData.enabled)
    await reloadPending()
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '无法读取项目概览' } finally { loading.value = false }
  if (query.value.trim()) await search()
})

async function search() {
  if (!workspace.activeProjectId || !query.value.trim()) return
  const projectId = workspace.activeProjectId
  const storyId = workspace.activeStory?.story_id || ''
  const branchId = workspace.activeBranchId || undefined
  const request = ++searchRequest
  const requestedScope = scopeKey(projectId, storyId, branchId || '')
  searching.value = true
  try {
    await router.replace({ query: { ...route.query, q: query.value.trim(), type: recordTypeFilter.value || undefined } })
    const data = await api.searchKnowledge(projectId, query.value.trim(), storyId, '', 40, recordTypeFilter.value, branchId)
    if (request !== searchRequest || requestedScope !== currentScopeKey()) return
    results.value = data.items as any[]
    selectedKnowledgeIds.value = []
    nextCursor.value = data.next_cursor || ''
  } catch (reason) {
    if (request !== searchRequest || requestedScope !== currentScopeKey()) return
    error.value = reason instanceof ApiClientError ? reason.message : '搜索失败'
  } finally {
    if (request === searchRequest && requestedScope === currentScopeKey()) searching.value = false
  }
}

function knowledgeId(item: any) { return String(item?.knowledge_id || item?.record_id || item?.id || '') }
function canPromote(item: any) {
  return item?.can_promote === true
}
function toggleKnowledge(item: any) {
  const id = knowledgeId(item)
  if (!id || !canPromote(item)) return
  selectedKnowledgeIds.value = selectedKnowledgeIds.value.includes(id) ? selectedKnowledgeIds.value.filter((candidate) => candidate !== id) : [...selectedKnowledgeIds.value, id]
}
async function promoteKnowledge(ids: string[] = selectedKnowledgeIds.value) {
  if (!workspace.activeProjectId || !ids.length || promoting.value) return
  promoting.value = true
  try { const data = await api.promoteKnowledge(workspace.activeProjectId, ids, undefined, workspace.activeStory?.story_id, workspace.activeBranchId || undefined); selectedKnowledgeIds.value = []; notify(`已共享 ${data.promoted_count || 0} 条知识到项目`, 'success'); await search() } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '共享到项目失败' } finally { promoting.value = false }
}

async function loadMoreSearch() {
  if (!workspace.activeProjectId || !query.value.trim() || !nextCursor.value || loadingMore.value) return
  const projectId = workspace.activeProjectId
  const storyId = workspace.activeStory?.story_id || ''
  const branchId = workspace.activeBranchId || undefined
  const requestedScope = scopeKey(projectId, storyId, branchId || '')
  const request = ++searchRequest
  loadingMore.value = true
  const cursor = nextCursor.value
  try {
    const data = await api.searchKnowledge(projectId, query.value.trim(), storyId, cursor, 40, recordTypeFilter.value, branchId)
    if (request !== searchRequest || requestedScope !== currentScopeKey()) return
    results.value = [...results.value, ...(data.items as any[])]
    nextCursor.value = data.next_cursor || ''
  } catch (reason) {
    if (request !== searchRequest || requestedScope !== currentScopeKey()) return
    error.value = reason instanceof ApiClientError ? reason.message : '加载更多失败'
  } finally {
    if (request === searchRequest && requestedScope === currentScopeKey()) loadingMore.value = false
  }
}

async function openDetail(item: any) {
  if (!workspace.activeProjectId || !item?.record_type || item?.record_id == null) return
  const projectId = workspace.activeProjectId
  const storyId = workspace.activeStory?.story_id || ''
  const branchId = workspace.activeBranchId || undefined
  const requestedScope = scopeKey(projectId, storyId, branchId || '')
  const request = ++detailRequest
  detailOwner.value = { projectId, storyId, branchId }
  detailLoading.value = true
  try {
    const recordType = String(item.record_type)
    const recordId = String(item.record_id)
    const detail = await api.knowledgeDetail(projectId, recordType, recordId, storyId, branchId)
    if (request !== detailRequest || requestedScope !== currentScopeKey()) return
    detailRecordType.value = recordType
    detailRecordId.value = recordId
    selectedDetail.value = detail
    detailJson.value = JSON.stringify((detail as any)?.payload || detail, null, 2)
    if (recordType !== 'knowledge') return
    const revisions = await api.knowledgeRevisions(projectId, recordType, recordId, storyId, branchId)
    if (request !== detailRequest || requestedScope !== currentScopeKey()) return
    detailRevisions.value = revisions.revisions
    const evidence = await api.knowledgeEvidence(projectId, recordType, recordId, storyId, branchId)
    if (request !== detailRequest || requestedScope !== currentScopeKey()) return
    detailEvidence.value = evidence.evidence
  } catch (reason) {
    if (request !== detailRequest || requestedScope !== currentScopeKey()) return
    error.value = reason instanceof ApiClientError ? reason.message : '无法读取知识详情'
  } finally {
    if (request === detailRequest && requestedScope === currentScopeKey()) detailLoading.value = false
  }
}

async function saveDetail() {
  const owner = detailOwner.value
  if (!owner.projectId || !owner.storyId || detailRecordType.value !== 'knowledge' || !detailRecordId.value || detailSaving.value || scopeKey() !== scopeKey(owner.projectId, owner.storyId, owner.branchId || '')) return
  const recordType = detailRecordType.value
  const recordId = detailRecordId.value
  const requestedScope = scopeKey(owner.projectId, owner.storyId, owner.branchId || '')
  detailSaving.value = true
  try {
    const patch = JSON.parse(detailJson.value) as Record<string, unknown>
    const saved = await api.updateKnowledge(owner.projectId, recordType, recordId, patch, undefined, undefined, owner.storyId, owner.branchId)
    if (requestedScope !== currentScopeKey()) return
    selectedDetail.value = saved.record
    detailRecordId.value = String(saved.record?.knowledge_id || saved.record?.record_id || recordId)
    const revisions = await api.knowledgeRevisions(owner.projectId, recordType, detailRecordId.value, owner.storyId, owner.branchId)
    if (requestedScope !== currentScopeKey()) return
    detailRevisions.value = revisions.revisions
  } catch (reason) {
    if (requestedScope !== currentScopeKey()) return
    error.value = reason instanceof Error ? reason.message : '知识保存失败'
  } finally {
    if (requestedScope === currentScopeKey()) detailSaving.value = false
  }
}

async function restoreRevision(revision: any) {
  const owner = detailOwner.value
  if (!owner.projectId || !owner.storyId || !detailRecordId.value || !revision?.revision_id || scopeKey() !== scopeKey(owner.projectId, owner.storyId, owner.branchId || '')) return
  const recordType = detailRecordType.value
  const recordId = detailRecordId.value
  const requestedScope = scopeKey(owner.projectId, owner.storyId, owner.branchId || '')
  try {
    await api.restoreKnowledgeRevision(owner.projectId, recordType, recordId, String(revision.revision_id), owner.storyId, owner.branchId)
    const refreshed = await api.knowledgeDetail(owner.projectId, recordType, recordId, owner.storyId, owner.branchId)
    if (requestedScope !== currentScopeKey()) return
    selectedDetail.value = refreshed
    detailJson.value = JSON.stringify((refreshed as any)?.payload || refreshed, null, 2)
    const evidence = await api.knowledgeEvidence(owner.projectId, recordType, recordId, owner.storyId, owner.branchId)
    if (requestedScope !== currentScopeKey()) return
    detailEvidence.value = evidence.evidence
  } catch (reason) {
    if (requestedScope !== currentScopeKey()) return
    error.value = reason instanceof Error ? reason.message : '修订恢复失败'
  }
}

function compareRevision(revision: any) {
  const snapshot = revision?.snapshot || revision?.payload || {}
  revisionDiff.value = `当前版本\n${detailJson.value}\n\n修订 ${revision?.revision_no || revision?.revision_id || ''}\n${JSON.stringify(snapshot, null, 2)}`
}

async function confirmPending(item: any) {
  if (!workspace.activeProjectId || !item?.pending_id || pendingBusy.value || pendingNeedsEntityResolution(item)) return
  pendingBusy.value = true
  try { await api.confirmPending(workspace.activeProjectId, [String(item.pending_id)], workspace.activeStory?.story_id, workspace.activeBranchId || undefined); pending.value = pending.value.filter((candidate) => candidate.pending_id !== item.pending_id) } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '确认知识失败' } finally { pendingBusy.value = false }
}

async function resolvePendingEntity(item: any) {
  const pendingId = String(item?.pending_id || '')
  const targetEntityId = pendingResolutionTarget(item)
  if (!workspace.activeProjectId || !pendingId || !targetEntityId || pendingBusy.value || resolvingPendingId.value) return
  resolvingPendingId.value = pendingId
  error.value = ''
  try {
    await api.resolvePendingEntity(
      workspace.activeProjectId,
      pendingId,
      targetEntityId,
      workspace.activeStory?.story_id,
      workspace.activeBranchId || undefined,
    )
    delete pendingResolution.value[pendingId]
    notify('已确认资料对应的实体，可继续审核。', 'success')
    await reloadPending()
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '实体对应确认失败'
  } finally {
    resolvingPendingId.value = ''
  }
}

async function discardPending(item: any) {
  if (!workspace.activeProjectId || !item?.pending_id || pendingBusy.value) return
  pendingBusy.value = true
  try { await api.discardPending(workspace.activeProjectId, [String(item.pending_id)], workspace.activeStory?.story_id, workspace.activeBranchId || undefined); pending.value = pending.value.filter((candidate) => candidate.pending_id !== item.pending_id) } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '忽略知识失败' } finally { pendingBusy.value = false }
}

async function copyCurrentStory() {
  if (!workspace.activeProjectId || !workspace.activeStory || copyingStory.value) return
  const name = await dialog.prompt({ title: '复制当前故事', message: '将复制结构、章节、摘要和讨论记录。项目级资料不会重复复制。', confirmLabel: '开始复制', input: { label: '新故事名称', initialValue: `${workspace.activeStory.name} · 副本` } })
  if (!name?.trim()) return
  copyingStory.value = true
  try {
    const result = await api.copyStory(workspace.activeProjectId, workspace.activeStory.story_id, { name: name.trim(), include_discussions: true, include_summaries: true, include_chapters: true })
    await workspace.loadStories()
    if (result.story?.story_id) await workspace.selectStory(result.story.story_id)
    notify('故事已复制并切换到新副本', 'success')
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '复制故事失败' } finally { copyingStory.value = false }
}
</script>

<template>
  <aside v-if="revisionDiff" class="revision-diff" role="dialog" aria-modal="true" aria-label="修订对比"><div><strong>修订对比</strong><button class="detail-close" @click="revisionDiff = ''">关闭</button></div><pre>{{ revisionDiff }}</pre></aside>
  <div v-if="selectedDetail && detailRevisions.length" class="revision-strip"><span>修订：</span><button v-for="revision in detailRevisions.slice(0, 5)" :key="`compare-${revision.revision_id}`" class="pending-button" @click="compareRevision(revision)">{{ revision.revision_no || revision.revision_id }}</button></div>
  <section class="shared-page">
    <p class="eyebrow">共享工作区</p>
    <div class="shared-heading">
      <div><h2>项目概览与知识</h2><p>规划和对话工作台共用这里的项目数据、知识和后台任务。</p></div>
      <div class="heading-actions"><span class="pill">{{ workspace.activeStory?.creation_mode === 'conversational' ? '对话模式' : '规划模式' }}</span><button class="button secondary" :disabled="copyingStory" @click="copyCurrentStory">{{ copyingStory ? '复制中…' : '复制故事' }}</button></div>
    </div>
    <div v-if="loading" class="shared-state">正在读取项目摘要…</div>
    <template v-else>
      <div class="summary-grid"><div><strong>{{ summary.chapter_count ?? 0 }}</strong><span>已写章节</span></div><div><strong>{{ summary.outline_exists ? '有' : '无' }}</strong><span>正式大纲</span></div><div><strong>{{ summary.knowledge_item_count ?? 0 }}</strong><span>知识条目</span></div><div><strong>{{ summary.resource_file_count ?? 0 }}</strong><span>资源文件</span></div></div>
      <div class="shared-columns">
        <div class="search-panel">
          <div><p class="eyebrow">知识搜索</p><h3>搜索当前故事和项目知识</h3></div>
          <div class="search-row"><input v-model="query" aria-label="搜索知识" placeholder="输入角色、地点或规则" @keydown.enter="search" /><select v-model="recordTypeFilter" aria-label="知识类型筛选"><option value="">全部类型</option><option value="knowledge">知识</option><option value="entity">实体</option><option value="source">来源</option></select><button class="button accent" :disabled="searching || !query.trim()" @click="search">{{ searching ? '检索中…' : '搜索' }}</button></div>
          <div class="result-area"><div v-if="selectedKnowledgeIds.length" class="bulk-actions"><span>已选 {{ selectedKnowledgeIds.length }} 条故事知识</span><button class="pending-button confirm" @click="promoteKnowledge()" :disabled="promoting">{{ promoting ? '共享中…' : '共享到项目' }}</button></div><div v-if="results.length" ref="resultViewport" class="result-list" @scroll="onResultScroll"><div :style="{ height: `${resultTopSpacer}px` }" aria-hidden="true"></div><div v-for="(item, index) in visibleResults" :key="item.id || `${resultStart}-${index}`" class="result-item" role="button" tabindex="0" @click="openDetail(item)" @keydown.enter="openDetail(item)"><input v-if="canPromote(item)" type="checkbox" :checked="selectedKnowledgeIds.includes(knowledgeId(item))" aria-label="选择知识条目" @click.stop @change="toggleKnowledge(item)" /><strong>{{ item.title || item.name || item.record_type || '知识条目' }}</strong><p>{{ item.summary || item.description || item.content || '打开查看详情' }}</p></div><div :style="{ height: `${resultBottomSpacer}px` }" aria-hidden="true"></div><button v-if="nextCursor" class="pending-button" :disabled="loadingMore" @click="loadMoreSearch">{{ loadingMore ? '加载中…' : '加载更多' }}</button></div></div>
          <p v-if="!results.length" class="muted search-empty">输入关键词后，结果会显示在这里。</p>
          <div v-if="detailLoading" class="detail-state">正在读取条目…</div>
          <article v-else-if="selectedDetail" class="knowledge-detail"><button class="detail-close" @click="selectedDetail = null">关闭</button><p class="eyebrow">知识详情</p><RouterLink v-if="detailRecordType === 'knowledge'" class="detail-typed-link" :to="{ name: workspace.mode === 'conversational' ? 'conversational-knowledge-editor' : 'planned-knowledge-editor', params: { recordType: detailRecordType, recordId: detailRecordId } }">打开知识编辑器</RouterLink><button v-if="canPromote(selectedDetail)" class="pending-button confirm" :disabled="promoting" @click="promoteKnowledge([detailRecordId])">共享到项目</button><textarea v-model="detailJson" class="detail-editor" aria-label="知识条目 JSON 编辑器"></textarea><div class="detail-actions"><button class="button accent" :disabled="detailSaving" @click="saveDetail">{{ detailSaving ? '保存中…' : '保存修订' }}</button><button v-for="revision in detailRevisions.slice(0, 3)" :key="revision.revision_id" class="pending-button" @click="restoreRevision(revision)">恢复修订 {{ revision.revision_no || revision.revision_id }}</button></div><pre>{{ JSON.stringify(selectedDetail, null, 2) }}</pre></article>
        </div>
        <div class="side-column">
          <div class="task-panel"><p class="eyebrow">后台任务</p><h3>任务与能力状态</h3><div class="task-counts"><span>资料导入 <strong>{{ tasks.ingestion.length }}</strong></span></div><div class="capability-list"><div v-for="(item, key) in capabilities" :key="key" class="capability-row"><i :class="{ ready: item.available }"></i><span>{{ capabilityLabel(String(key)) }}</span><small>{{ item.available ? '可用' : (item.message || item.status) }}</small></div></div></div>
          <div class="pending-panel"><p class="eyebrow">待审核知识</p><h3>候选条目 <small>{{ pending.length }}</small></h3><p v-if="!pending.length" class="muted">暂无待审核条目。</p><div v-for="item in pending.slice(0, 5)" :key="item.pending_id" class="pending-row"><div><strong>{{ item.name || '未命名条目' }}</strong><small>{{ item.category || '知识' }} · {{ item.source_title || '当前会话' }}</small><div v-if="pendingNeedsEntityResolution(item)" class="pending-resolution"><small>{{ pendingResolutionPrompt(item) }}</small><select v-model="pendingResolution[String(item.pending_id)]" :aria-label="`${item.name || '候选条目'}对应实体`"><option value="">选择世界线/实体</option><option v-for="option in pendingResolutionOptions(item)" :key="option.entity_id" :value="option.entity_id">{{ pendingResolutionLabel(option) }}</option></select><button class="pending-button confirm" :disabled="pendingBusy || resolvingPendingId === item.pending_id || !pendingResolutionTarget(item)" @click="resolvePendingEntity(item)">{{ resolvingPendingId === item.pending_id ? '确认中…' : '确认对应实体' }}</button></div><small v-else-if="item.entity_resolution_status" class="pending-resolution-ok">实体对应已确认</small></div><div><button class="pending-button confirm" :disabled="pendingBusy || pendingNeedsEntityResolution(item)" @click="confirmPending(item)">确认</button><button class="pending-button" :disabled="pendingBusy || resolvingPendingId === item.pending_id" @click="discardPending(item)">忽略</button></div></div></div>
        </div>
      </div>
    </template>
    <p v-if="error" class="shared-error">{{ error }}</p>
  </section>
</template>

<style scoped>
.shared-page { max-width: 1120px; margin: 0 auto; padding: 10px 0 50px; }.shared-heading { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin: 12px 0 35px; }.shared-heading h2 { margin: 0; font-family: Georgia, serif; font-size: clamp(34px, 5vw, 56px); font-weight: 400; letter-spacing: -.05em; }.shared-heading p { margin: 15px 0 0; color: var(--muted, #8b8175); font-size: 13px; }.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }.summary-grid div { display: grid; gap: 6px; padding: 20px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 15px; background: rgba(255,255,255,.06); }.summary-grid strong { font-family: Georgia, serif; font-size: 28px; font-weight: 400; }.summary-grid span { color: var(--muted, #8b8175); font-size: 11px; }.search-panel { margin-top: 18px; padding: 24px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 18px; background: rgba(255,255,255,.05); }.search-panel h3 { margin: 5px 0 18px; font-family: Georgia, serif; font-size: 23px; font-weight: 400; }.search-row { display: flex; gap: 9px; }.search-row input { flex: 1; min-width: 0; padding: 12px 14px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 10px; outline: 0; color: inherit; background: transparent; }.result-list { display: grid; gap: 8px; margin-top: 18px; }.result-list article { padding: 14px; border-radius: 11px; background: rgba(255,255,255,.05); }.result-list p { margin: 6px 0 0; color: var(--muted, #8b8175); font-size: 12px; line-height: 1.6; }.search-empty { margin: 17px 0 0; font-size: 12px; }.shared-state { min-height: 180px; display: grid; place-items: center; color: var(--muted, #8b8175); font-size: 13px; }.shared-error { color: #d98e76; font-size: 12px; }
.revision-strip { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; max-width: 1120px; margin: 0 auto 10px; color: var(--muted, #8b8175); font-size: 10px; }.revision-diff { position: fixed; z-index: 10; inset: 10% 10%; padding: 18px; overflow: auto; border: 1px solid var(--line); border-radius: 14px; background: #282b29; box-shadow: 0 20px 80px rgba(0,0,0,.45); }.revision-diff > div { display: flex; align-items: center; justify-content: space-between; color: #dfc0a9; font-size: 12px; }.revision-diff pre { margin-top: 12px; color: #c6c0b8; font: 11px/1.6 ui-monospace, monospace; white-space: pre-wrap; }
.heading-actions { display: flex; align-items: center; gap: 10px; }
@media (max-width: 680px) { .shared-heading { align-items: flex-start; flex-direction: column; }.summary-grid { grid-template-columns: repeat(2, 1fr); }.search-row { align-items: stretch; flex-direction: column; } }
</style>

<style scoped>
.shared-columns { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(260px, .8fr); gap: 18px; }
.shared-columns .search-panel { margin-top: 18px; }
.task-panel { margin-top: 18px; padding: 24px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 18px; background: rgba(255,255,255,.05); }
.task-panel h3 { margin: 5px 0 18px; font-family: Georgia, serif; font-size: 23px; font-weight: 400; }
.task-counts { display: grid; gap: 8px; color: var(--muted, #8b8175); font-size: 12px; }
.task-counts span { display: flex; justify-content: space-between; padding-bottom: 8px; border-bottom: 1px solid var(--line, rgba(255,255,255,.1)); }
.task-counts strong { color: inherit; font-family: Georgia, serif; font-size: 17px; font-weight: 400; }
.capability-list { display: grid; gap: 7px; margin-top: 20px; }
.capability-row { display: grid; grid-template-columns: 8px 1fr auto; align-items: center; gap: 7px; color: var(--muted, #8b8175); font-size: 11px; }
.capability-row i { width: 6px; height: 6px; border-radius: 50%; background: #b66d58; }.capability-row i.ready { background: #7da477; }.capability-row small { max-width: 130px; overflow: hidden; color: var(--muted, #8b8175); text-overflow: ellipsis; white-space: nowrap; }
.result-item { width: 100%; padding: 14px; border: 0; border-radius: 11px; color: inherit; background: rgba(255,255,255,.05); cursor: pointer; text-align: left; }.result-item:hover { background: rgba(255,255,255,.1); }.knowledge-detail { position: relative; margin-top: 15px; padding: 18px; border: 1px solid var(--line, rgba(255,255,255,.12)); border-radius: 12px; background: rgba(0,0,0,.08); }.knowledge-detail pre { max-height: 300px; margin: 12px 0 0; overflow: auto; color: var(--muted, #8b8175); font: 11px/1.6 ui-monospace, monospace; white-space: pre-wrap; }.detail-close { position: absolute; top: 12px; right: 12px; border: 0; color: var(--muted, #8b8175); background: transparent; cursor: pointer; font-size: 11px; }.detail-state { margin-top: 15px; color: var(--muted, #8b8175); font-size: 11px; }
.result-area { margin-top: 18px; }.bulk-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; color: var(--muted); font-size: 11px; }.result-item input { margin-right: 7px; accent-color: var(--accent); }
.detail-editor { width: 100%; min-height: 180px; margin-top: 12px; padding: 12px; resize: vertical; border: 1px solid var(--line, rgba(255,255,255,.12)); border-radius: 8px; color: inherit; background: rgba(0,0,0,.12); font: 11px/1.6 ui-monospace, monospace; }.detail-actions { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 10px; }
.pending-panel { margin-top: 18px; padding: 22px 24px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 18px; background: rgba(255,255,255,.05); }.pending-panel h3 { margin: 5px 0 15px; font-family: Georgia, serif; font-size: 22px; font-weight: 400; }.pending-panel h3 small { margin-left: 6px; color: var(--muted, #8b8175); font: 11px inherit; }.pending-row { display: flex; align-items: center; justify-content: space-between; gap: 15px; padding: 11px 0; border-top: 1px solid var(--line, rgba(255,255,255,.1)); }.pending-row strong, .pending-row small { display: block; }.pending-row strong { font-size: 12px; }.pending-row small { margin-top: 4px; color: var(--muted, #8b8175); font-size: 10px; }.pending-button { padding: 6px 9px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 7px; color: var(--muted, #8b8175); background: transparent; cursor: pointer; font-size: 10px; }.pending-button.confirm { color: #7da477; }.pending-button + .pending-button { margin-left: 5px; }
@media (max-width: 820px) { .shared-columns { grid-template-columns: 1fr; } }
.result-list { display: block; max-height: 520px; margin-top: 18px; overflow: auto; contain: strict; }
:global(html:not(.novelforge-developer)) .knowledge-detail .detail-editor,
:global(html:not(.novelforge-developer)) .knowledge-detail .detail-actions,
:global(html:not(.novelforge-developer)) .knowledge-detail > pre { display: none; }
:global(html:not(.novelforge-developer)) .knowledge-detail::after { content: '普通视图已隐藏原始 JSON；请使用类型化编辑器。'; display: block; margin-top: 14px; color: var(--muted); font-size: 11px; line-height: 1.6; }
.detail-safe-note { margin-top: 14px; color: var(--muted); font-size: 11px; line-height: 1.6; }
.detail-typed-link { display: block; max-width: 1120px; margin: 8px auto; color: var(--accent); font-size: 11px; }
.pending-resolution { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }.pending-resolution select { max-width: 300px; padding: 5px 7px; border: 1px solid var(--line, rgba(255,255,255,.13)); border-radius: 7px; color: inherit; background: transparent; font-size: 10px; }.pending-resolution-ok { color: #7da477; }
</style>
