<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'
import MaterialImportForm from '../components/MaterialImportForm.vue'
import { dialog } from '../ui/dialog'
import { ingestionEstimateLabel, ingestionProgressSuffix, ingestionStatusCanRetry, ingestionStatusLabel } from '../ui/ingestionStatus'

const workspace = useWorkspaceStore()
const workbench = ref<Record<string, any>>({})
const attachments = ref<any[]>([])
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const shareMessage = ref('')
const retryingId = ref('')
const selectedAttachmentIds = ref<string[]>([])
const sharingAttachments = ref(false)
const referenceLibraries = ref<any[]>([])
const storyBindings = ref<any[]>([])
const referenceLoading = ref(false)
const bindingBusyId = ref('')
const referenceMessage = ref('')
const releaseSources = ref<Record<string, any[]>>({})
const sourceLoadingId = ref('')
const archivingLibraryId = ref('')
let pollTimer: ReturnType<typeof globalThis.setTimeout> | undefined
let loadToken = 0
let referenceToken = 0
let disposed = false

function attachmentCanRetry(item: any) {
  return ingestionStatusCanRetry(item)
}

async function load() {
  const projectId = workspace.activeProjectId
  const storyId = workspace.activeStory?.story_id
  const branchId = workspace.activeBranchId || undefined
  if (!projectId || refreshing.value) return
  const token = ++loadToken
  refreshing.value = true
  try {
    const [workbenchData, attachmentData] = await Promise.all([
      api.ingestionWorkbench(projectId),
      api.ingestionAttachments(projectId, storyId),
    ])
    if (disposed || token !== loadToken || workspace.activeProjectId !== projectId || workspace.activeStory?.story_id !== storyId || (workspace.activeBranchId || undefined) !== branchId) return
    workbench.value = workbenchData
    attachments.value = attachmentData.attachments || []
    await loadReferenceLibraries(projectId, storyId, branchId)
    error.value = ''
  } catch (reason) {
    if (!disposed && token === loadToken && workspace.activeProjectId === projectId && workspace.activeStory?.story_id === storyId && (workspace.activeBranchId || undefined) === branchId) error.value = reason instanceof ApiClientError ? reason.message : '无法读取资料导入状态'
  } finally {
    if (token === loadToken) {
      refreshing.value = false
      loading.value = false
    }
  }
}

async function loadReferenceLibraries(projectId = workspace.activeProjectId, storyId = workspace.activeStory?.story_id, branchId = workspace.activeBranchId || undefined) {
  if (!projectId || !storyId) { referenceLibraries.value = []; storyBindings.value = []; return }
  const requestedBranchId = branchId
  const token = ++referenceToken
  referenceLoading.value = true
  let releaseLoadFailed = false
  try {
    const [libraryData, bindingData] = await Promise.all([
      api.referenceLibraries(projectId),
      api.storyReferenceLibraries(projectId, storyId, requestedBranchId, true),
    ])
    const libraries = libraryData.libraries || []
    const enriched = await Promise.all(libraries.map(async (library) => {
      try {
        const releases = (await api.referenceLibraryReleases(projectId, String(library.library_id))).releases || []
        const ready = releases.filter((release) => String(release.status || 'ready') === 'ready').sort((left, right) => Number(right.release_no || 0) - Number(left.release_no || 0))
        return { ...library, releases, latestRelease: ready[0] || null }
      } catch (_reason) { releaseLoadFailed = true; return { ...library, releases: [], latestRelease: null } }
    }))
    if (token !== referenceToken || workspace.activeProjectId !== projectId || workspace.activeStory?.story_id !== storyId || (workspace.activeBranchId || undefined) !== requestedBranchId) return
    referenceLibraries.value = enriched
    storyBindings.value = bindingData.bindings || []
    releaseSources.value = {}
    if (releaseLoadFailed) referenceMessage.value = '资料副本加载失败：版本列表读取失败，请重试。'
  } catch (reason) {
    referenceLibraries.value = []
    storyBindings.value = []
    if (token === referenceToken && workspace.activeProjectId === projectId && workspace.activeStory?.story_id === storyId && (workspace.activeBranchId || undefined) === requestedBranchId) referenceMessage.value = reason instanceof ApiClientError ? `资料副本加载失败：${reason.message}` : '资料副本加载失败，请刷新重试。'
  } finally { if (token === referenceToken) referenceLoading.value = false }
}

function releaseItemCount(release: any) {
  const raw = release?.manifest_json ?? release?.manifest
  if (raw && typeof raw === 'object') return raw.item_count || raw.knowledge_ids?.length || '若干'
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return parsed?.item_count || parsed?.knowledge_ids?.length || '若干'
    } catch (_reason) { return '若干' }
  }
  return '若干'
}

function branchBinding(binding: any) {
  return String(binding?.branch_id || '') === String(workspace.activeBranchId || '')
}
function bindingFor(library: any) {
  return storyBindings.value.find((binding) => String(binding.library_id) === String(library.library_id) && branchBinding(binding) && binding.status !== 'archived')
}
function libraryNeedsUpdate(library: any) {
  const binding = bindingFor(library)
  const latestReleaseId = String(library?.latestRelease?.release_id || '')
  return Boolean(binding && latestReleaseId && String(binding.release_id || '') !== latestReleaseId)
}
function sourceTitle(source: any) {
  const sourceJson = source?.source_json && typeof source.source_json === 'object' ? source.source_json : {}
  return String(sourceJson.title || sourceJson.name || source?.title || source?.source_id || '未命名来源')
}
async function viewReleaseSources(library: any) {
  const projectId = workspace.activeProjectId
  const libraryId = String(library?.library_id || '')
  const releaseId = String(library?.latestRelease?.release_id || '')
  const requestedStoryId = workspace.activeStory?.story_id
  const requestedBranchId = workspace.activeBranchId || undefined
  if (!projectId || !libraryId || !releaseId || sourceLoadingId.value) return
  sourceLoadingId.value = libraryId
  try {
    const data = await api.referenceLibraryReleaseSources(projectId, libraryId, releaseId)
    if (workspace.activeProjectId === projectId && workspace.activeStory?.story_id === requestedStoryId && (workspace.activeBranchId || undefined) === requestedBranchId) releaseSources.value = { ...releaseSources.value, [libraryId]: data.sources || [] }
  } catch (reason) {
    if (workspace.activeProjectId === projectId && workspace.activeStory?.story_id === requestedStoryId && (workspace.activeBranchId || undefined) === requestedBranchId) referenceMessage.value = reason instanceof ApiClientError ? `来源查证加载失败：${reason.message}` : '来源查证加载失败，请重试。'
  } finally { sourceLoadingId.value = '' }
}
async function useLibrary(library: any) {
  const projectId = workspace.activeProjectId
  const storyId = workspace.activeStory?.story_id
  const releaseId = String(library?.latestRelease?.release_id || library?.latest_release_id || '')
  if (!projectId || !storyId || !library?.library_id || !releaseId || bindingBusyId.value) {
    if (!releaseId) referenceMessage.value = '这份资料还没有已确认的版本，完成自动提炼后才能用于当前故事。'
    return
  }
  bindingBusyId.value = String(library.library_id)
  referenceMessage.value = ''
  try {
    await api.bindReferenceLibrary(projectId, storyId, String(library.library_id), { release_id: releaseId, branch_id: workspace.activeBranchId || undefined, idempotency_key: `vue-${storyId}-${workspace.activeBranchId || 'story'}-${library.library_id}-${releaseId}` })
    referenceMessage.value = `已将“${library.title || '资料'}”复制为当前故事的私有副本。`
    await loadReferenceLibraries(projectId, storyId, workspace.activeBranchId || undefined)
  } catch (reason) { referenceMessage.value = reason instanceof ApiClientError ? reason.message : '资料副本创建失败' }
  finally { bindingBusyId.value = '' }
}

async function unbindLibrary(binding: any) {
  const projectId = workspace.activeProjectId
  const storyId = workspace.activeStory?.story_id
  if (!projectId || !storyId || !binding?.binding_id || bindingBusyId.value) return
  if (!await dialog.confirm({ title: '解除当前故事使用？', message: '会停止将这份资料副本放入当前故事上下文，项目原文、公共资料和已保存正文都会保留。', confirmLabel: '解除使用' })) return
  bindingBusyId.value = String(binding.library_id)
  try { await api.unbindReferenceLibrary(projectId, storyId, String(binding.binding_id), workspace.activeBranchId || undefined); referenceMessage.value = '已解除当前故事使用，私有副本历史仍保留。'; await loadReferenceLibraries(projectId, storyId, workspace.activeBranchId || undefined) }
  catch (reason) { referenceMessage.value = reason instanceof ApiClientError ? reason.message : '解除资料使用失败' }
  finally { bindingBusyId.value = '' }
}

async function archiveLibrary(library: any) {
  const projectId = workspace.activeProjectId
  const libraryId = String(library?.library_id || '')
  if (!projectId || !libraryId || archivingLibraryId.value) return
  if (!await dialog.confirm({
    title: '归档项目资料？',
    message: '归档后不会删除已有故事的独立副本；项目资料将从可用于新故事的列表中隐藏。',
    confirmLabel: '归档资料',
  })) return
  archivingLibraryId.value = libraryId
  try {
    await api.archiveReferenceLibrary(projectId, libraryId)
    referenceMessage.value = '项目资料已归档；已有故事的独立副本不受影响。'
    await loadReferenceLibraries(projectId, workspace.activeStory?.story_id, workspace.activeBranchId || undefined)
  } catch (reason) {
    referenceMessage.value = reason instanceof ApiClientError ? reason.message : '资料归档失败，请重试。'
  } finally { archivingLibraryId.value = '' }
}

function canShareAttachment(item: any) {
  if (typeof item?.can_promote === 'boolean') return item.can_promote
  return String(item?.scope || item?.attachment_scope || '') === 'story' && String(item?.story_id || '') === String(workspace.activeStory?.story_id || '') && Number(item?.confirmed_knowledge_count || item?.extracted_knowledge_count || item?.knowledge_count || 0) > 0 && Boolean(item?.attachment_id || item?.id)
}
function attachmentId(item: any) { return String(item?.attachment_id || item?.id || '') }
function toggleAttachment(item: any) {
  if (!canShareAttachment(item)) return
  const id = attachmentId(item)
  selectedAttachmentIds.value = selectedAttachmentIds.value.includes(id) ? selectedAttachmentIds.value.filter((candidate) => candidate !== id) : [...selectedAttachmentIds.value, id]
}
async function shareAttachments(ids: string[] = selectedAttachmentIds.value) {
  const projectId = workspace.activeProjectId
  if (!projectId || !ids.length || sharingAttachments.value) return
  sharingAttachments.value = true
  try {
    let promoted = 0
    for (const id of ids) promoted += Number((await api.promoteKnowledge(projectId, [], id)).promoted_count || 0)
    selectedAttachmentIds.value = []
    shareMessage.value = promoted ? `已共享 ${promoted} 条资料知识到项目。` : '没有可共享的新知识。'
    await load()
  } catch (reason) { shareMessage.value = reason instanceof ApiClientError ? reason.message : '资料共享到项目失败' } finally { sharingAttachments.value = false }
}

function startPolling() {
  stopPolling()
  if (disposed || Number(workbench.value.active_task_count || 0) <= 0) return
  pollTimer = globalThis.setTimeout(async () => { await load(); startPolling() }, 3500)
}

function stopPolling() {
  if (pollTimer !== undefined) globalThis.clearTimeout(pollTimer)
  pollTimer = undefined
}

async function onImported() {
  await load()
  startPolling()
}

async function retryAttachment(item: any) {
  const projectId = workspace.activeProjectId
  const attachmentId = String(item?.attachment_id || item?.id || '')
  if (!projectId || !attachmentId || retryingId.value) return
  const backgroundStatus = String(item?.metadata?.background_status || item?.background_status || '').toLowerCase()
  let confirmOverBudget = false
  if (backgroundStatus === 'awaiting_confirmation') {
    const estimate = item?.metadata?.background_estimate || item?.background_estimate || {}
    const detail = ingestionEstimateLabel(estimate)
    if (!await dialog.confirm({ title: '确认继续处理？', message: `${detail}。确认后会继续资料提炼。`, confirmLabel: '确认继续' })) return
    confirmOverBudget = true
  }
  retryingId.value = attachmentId
  try { await api.retryAttachment(projectId, attachmentId, confirmOverBudget); await load(); startPolling() } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '资料重试失败' } finally { retryingId.value = '' }
}

onMounted(async () => { await load(); startPolling() })
watch(() => `${workspace.activeProjectId || ''}:${workspace.activeStory?.story_id || ''}:${workspace.activeBranchId || ''}`, () => {
  stopPolling()
  loadToken += 1
  referenceToken += 1
  refreshing.value = false
  loading.value = true
  workbench.value = {}
  attachments.value = []
  selectedAttachmentIds.value = []
  referenceLibraries.value = []
  storyBindings.value = []
  referenceMessage.value = ''
  void load().then(startPolling)
})
onUnmounted(() => { disposed = true; loadToken += 1; stopPolling() })
</script>

<template>
  <section class="import-page">
    <div class="import-heading">
      <div><p class="eyebrow">资料库 · 导入资料</p><h1>把参考资料变成<em>项目知识</em></h1><p>粘贴资料或导入文件后，NovelForge 会自动提炼知识。知识可参与检索，原文只用于来源查证。</p></div>
      <button class="button secondary" :disabled="refreshing" @click="load">{{ refreshing ? '刷新中…' : '刷新状态' }}</button>
    </div>
    <MaterialImportForm v-if="workspace.activeProjectId && workspace.activeStory" :project-id="workspace.activeProjectId" :story-id="workspace.activeStory.story_id" mode="library" @imported="onImported" />
    <section v-if="workspace.activeStory" class="reference-panel" aria-label="用于当前故事"><div class="panel-heading"><div><p class="eyebrow">资料副本</p><h2>用于当前故事</h2><p class="muted">项目资料保持公共版本；使用后会成为当前故事{{ workspace.activeBranch?.name ? ` · ${workspace.activeBranch.name}` : '' }}的独立副本。原文仍只用于查证。</p></div><span v-if="referenceLoading" class="muted">同步中…</span></div><p v-if="!referenceLibraries.length && !referenceLoading && !referenceMessage" class="muted">暂无可用的已确认项目资料。导入并完成自动提炼后，这里会出现一键复制入口。</p><div v-for="library in referenceLibraries" :key="library.library_id" class="reference-row"><div><strong>{{ library.title || '未命名资料' }}</strong><small v-if="library.latestRelease">已确认版本 {{ library.latestRelease.release_no || '—' }} · {{ releaseItemCount(library.latestRelease) }} 条知识 <span v-if="libraryNeedsUpdate(library)" class="reference-update">有新版本可用</span></small><small v-else>等待已确认版本；当前不能用于故事</small><div v-if="releaseSources[library.library_id]?.length" class="reference-sources"><span>冻结来源查证：</span><span v-for="source in releaseSources[library.library_id]" :key="`${source.source_id}-${source.revision_id}`">{{ sourceTitle(source) }}{{ source.content_hash_verified ? ' · 已校验' : '' }}</span></div></div><div class="reference-actions"><button v-if="library.latestRelease" class="link-button" :disabled="sourceLoadingId === library.library_id" @click="viewReleaseSources(library)">{{ sourceLoadingId === library.library_id ? '读取中…' : '查看来源' }}</button><div v-if="bindingFor(library)" class="reference-bound"><span>已用于当前故事<span v-if="libraryNeedsUpdate(library)" class="reference-update"> · 需手动更新</span></span><button class="link-button" :disabled="Boolean(bindingBusyId)" @click="unbindLibrary(bindingFor(library))">{{ bindingBusyId === library.library_id ? '处理中…' : '解除使用' }}</button></div><button v-else class="link-button" :disabled="Boolean(bindingBusyId) || !library.latestRelease" @click="useLibrary(library)">{{ bindingBusyId === library.library_id ? '复制中…' : '用于当前故事' }}</button><button class="link-button archive-library" :disabled="Boolean(bindingBusyId) || archivingLibraryId === library.library_id" @click="archiveLibrary(library)">{{ archivingLibraryId === library.library_id ? '归档中…' : '归档项目资料' }}</button></div></div><p v-if="referenceMessage" class="import-message" role="status">{{ referenceMessage }}</p></section>
    <div v-if="loading" class="import-state">正在读取资料状态…</div>
    <template v-else>
      <section class="status-panel">
        <div><p class="eyebrow">导入状态</p><h2>项目资料处理进度</h2><p class="muted">当前项目固定保存为项目资料；后台任务会持续更新解析、知识提取和异常状态。</p></div>
        <div class="status-stats"><span>批次 <strong>{{ (workbench.batch_rows || []).length }}</strong></span><span>进行中 <strong>{{ workbench.active_task_count || 0 }}</strong></span><span>失败/部分异常 <strong>{{ workbench.failed_task_count || 0 }}</strong></span><span>资料条目 <strong>{{ attachments.length }}</strong></span></div>
      </section>
      <section v-if="attachments.length" class="attachment-panel"><div class="panel-heading"><div><p class="eyebrow">最近导入的资料</p><h2>处理记录</h2></div><div class="attachment-bulk"><span class="muted">自动提炼知识</span><button v-if="selectedAttachmentIds.length" class="link-button" :disabled="sharingAttachments" @click="shareAttachments()">{{ sharingAttachments ? '共享中…' : '共享到项目' }}</button></div></div><article v-for="item in attachments.slice(0, 12)" :key="item.attachment_id || item.id || item.relative_path" class="attachment-row"><div><input v-if="canShareAttachment(item)" type="checkbox" :checked="selectedAttachmentIds.includes(attachmentId(item))" aria-label="选择资料条目" @change="toggleAttachment(item)" /><strong>{{ item.title || item.filename || item.relative_path || '未命名资料' }}</strong><small>{{ ingestionStatusLabel(item) }}{{ ingestionProgressSuffix(item) }}</small></div><button v-if="canShareAttachment(item)" class="link-button" :disabled="sharingAttachments" @click="shareAttachments([attachmentId(item)])">共享到项目</button><span v-if="item.error || item.error_message" class="row-error">{{ item.error || item.error_message }}</span><button v-if="attachmentCanRetry(item)" class="link-button" @click="retryAttachment(item)" :disabled="retryingId === String(item.attachment_id || item.id)" >{{ retryingId === String(item.attachment_id || item.id) ? '重试中…' : '重试' }}</button></article></section>
      <section v-if="(workbench.batch_rows || []).length" class="batch-panel"><div class="panel-heading"><div><p class="eyebrow">后台任务</p><h2>批次处理</h2></div></div><article v-for="row in (workbench.batch_rows || []).slice(0, 8)" :key="row.batch_id" class="batch-row"><div><strong>{{ row.title || '资料批次' }}</strong><small>{{ row.status_label || ingestionStatusLabel(row) }} · {{ row.completed_count || 0 }}/{{ row.segment_count || 0 }} 项</small></div><span v-if="row.error_count" class="row-error">{{ row.error_count }} 项异常，可稍后重试</span></article></section>
    </template>
    <p v-if="shareMessage" class="import-message" role="status">{{ shareMessage }}</p><p v-if="error" class="import-error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.import-page { max-width: 1120px; margin: 0 auto; padding: 12px 0 60px; }
.import-heading { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 32px; }
.import-heading > .button { flex-shrink: 0; white-space: nowrap; }
.import-heading h1 { max-width: 760px; margin: 10px 0 16px; font-family: Georgia, serif; font-size: clamp(36px, 5vw, 62px); font-weight: 400; letter-spacing: -.055em; line-height: 1.08; }
.import-heading h1 em { color: var(--accent); font-style: normal; }
.import-heading p:not(.eyebrow) { max-width: 650px; color: var(--muted); font-size: 13px; line-height: 1.8; }
.import-state { min-height: 160px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }
.status-panel, .attachment-panel, .batch-panel { display: grid; gap: 15px; margin-top: 16px; padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }
.reference-panel { display: grid; gap: 13px; margin-top: 16px; padding: 22px; border: 1px solid rgba(143,174,137,.28); border-radius: 16px; background: rgba(125,164,119,.055); }
.reference-panel h2 { margin: 5px 0 7px; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }
.reference-row { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px 0; border-top: 1px solid var(--line); }
.reference-row strong, .reference-row small { display: block; }.reference-row strong { font-size: 12px; font-weight: 500; }.reference-row small { margin-top: 4px; color: var(--muted); font-size: 10px; }.reference-actions { display: flex; align-items: center; gap: 12px; white-space: nowrap; }.reference-bound { display: flex; align-items: center; gap: 10px; color: #8fae89; font-size: 10px; white-space: nowrap; }.reference-update { color: #e4b17c; }.reference-sources { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 7px; color: #a8b9a3; font-size: 10px; }
.status-panel h2, .attachment-panel h2, .batch-panel h2 { margin: 5px 0 7px; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }
.muted { color: var(--muted); font-size: 11px; line-height: 1.6; }
.status-stats { display: flex; flex-wrap: wrap; gap: 14px; color: var(--accent); font-size: 11px; }
.status-stats strong { margin-left: 3px; font-family: Georgia, serif; font-size: 18px; font-weight: 400; }
.panel-heading { display: flex; align-items: start; justify-content: space-between; gap: 12px; }
.attachment-bulk { display: flex; align-items: center; gap: 10px; }.attachment-row input { margin-right: 7px; accent-color: var(--accent); }
.attachment-row, .batch-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; border-top: 1px solid var(--line); }
.attachment-row strong, .attachment-row small, .batch-row strong, .batch-row small { display: block; }
.attachment-row strong, .batch-row strong { min-width: 0; overflow: hidden; font-size: 12px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.attachment-row small, .batch-row small { margin-top: 4px; color: var(--muted); font-size: 10px; }
.row-error { max-width: 35%; color: #d18d82; font-size: 10px; text-align: right; }
.link-button { padding: 0; border: 0; color: var(--accent); background: transparent; cursor: pointer; font-size: 10px; }
.import-error { color: #d18d82; font-size: 12px; }
.import-message { color: #8fae89; font-size: 12px; }
@media (max-width: 680px) { .import-heading { align-items: flex-start; flex-direction: column; }.attachment-row, .batch-row { align-items: flex-start; flex-wrap: wrap; }.row-error { max-width: 100%; text-align: left; } }
</style>
