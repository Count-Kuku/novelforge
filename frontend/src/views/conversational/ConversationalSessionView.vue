<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWorkspaceStore } from '../../stores/workspace'
import { api, ApiClientError } from '../../api/client'
import type { CreativeAction, CreativeFragment, CreativeTurn } from '../../types'
import { dialog } from '../../ui/dialog'

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()
const turns = ref<CreativeTurn[]>([])
const fragments = ref<CreativeFragment[]>([])
const loading = ref(true)
const error = ref('')
const extractingId = ref('')
const extractNotice = ref('')
const draft = ref('')
const sending = ref(false)
const cancelling = ref(false)
const operationId = ref('')
const cancelledByUser = ref(false)
const streamingText = ref('')
const activeFragmentId = ref('')
const startFromId = ref('')
const extractBlocked = ref<{ ids: string[]; count: number; sample: string }>({ ids: [], count: 0, sample: '' })
const composing = ref(false)
const attachmentOpen = ref(false)
const attachmentText = ref('')
const attachmentUrl = ref('')
const attachmentFile = ref<HTMLInputElement | null>(null)
const attachmentTitle = ref('粘贴资料')
const attachmentSaving = ref(false)
const batchUploadMessage = ref('')
const attachments = ref<any[]>([])
const sessionTitle = ref('')
const actions = ref<CreativeAction[]>([])
const contextOpen = ref(false)
const contextLoading = ref(false)
const contextData = ref<Record<string, any> | null>(null)
const timelineItems = computed(() => [
  ...turns.value.map((item) => ({ kind: 'turn' as const, id: item.turn_id, createdAt: item.created_at, item })),
  ...fragments.value.map((item) => ({ kind: 'fragment' as const, id: item.fragment_id, createdAt: item.created_at, item })),
].sort((left, right) => String(left.createdAt || '').localeCompare(String(right.createdAt || ''))))

const activeDraft = computed(() => {
  if (!activeFragmentId.value) return null
  const item = fragments.value.find((fragment) => fragment.fragment_id === activeFragmentId.value)
  return item && item.status === 'proposed' ? item : null
})
const hasConfirmedText = computed(() => fragments.value.some((fragment) => fragment.status === 'accepted' || fragment.status === 'finalized'))
const confirmedStarts = computed(() =>
  fragments.value
    .map((fragment, index) => ({
      fragment_id: fragment.fragment_id,
      vNo: index + 1,
      short: fragment.content.replace(/\s+/g, ' ').slice(0, 14),
    }))
    .filter((_item, index) => {
      const status = fragments.value[index].status
      return status === 'accepted' || status === 'finalized'
    }),
)
const composerModeHint = computed(() => {
  if (activeDraft.value) return '修订当前草稿：发送消息会替换这段候选'
  if (!fragments.value.length || !hasConfirmedText.value) return '起草新片段：将从故事开头生成'
  return ''
})

function syncStartFrom() {
  if (!hasConfirmedText.value) {
    startFromId.value = ''
    return
  }
  const confirmed = fragments.value.filter((fragment) => fragment.status === 'accepted' || fragment.status === 'finalized')
  if (activeFragmentId.value && confirmed.some((fragment) => fragment.fragment_id === activeFragmentId.value)) {
    startFromId.value = activeFragmentId.value
  } else {
    startFromId.value = confirmed[confirmed.length - 1]?.fragment_id || ''
  }
}

async function reloadBundle() {
  if (!workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  const data = await api.session(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId))
  turns.value = data.turns
  fragments.value = data.fragments
  attachments.value = data.attachments || []
  sessionTitle.value = data.session?.title || ''
  activeFragmentId.value = String(data.session?.active_fragment_id || '')
  syncStartFrom()
  try { actions.value = (await api.actions(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId))).actions } catch (reason) { actions.value = []; console.warn('Action list unavailable', reason) }
}

onMounted(async () => {
  if (!workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  try {
    await reloadBundle()
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '无法读取这段对话'
  } finally {
    loading.value = false
  }
})

async function send() {
  if (!draft.value.trim() || sending.value || !workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  const message = draft.value.trim()
  draft.value = ''
  sending.value = true
  cancelling.value = false
  operationId.value = ''
  cancelledByUser.value = false
  streamingText.value = ''
  error.value = ''
  try {
    const draftActive = Boolean(activeDraft.value)
    let actionType: string
    if (draftActive) actionType = 'rewrite'
    else if (!hasConfirmedText.value) actionType = 'generate'
    else {
      actionType = 'continue'
      const fromId = startFromId.value || activeFragmentId.value
      if (fromId && fromId !== activeFragmentId.value) {
        const frontierData = await api.selectFrontier(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId), fromId)
        activeFragmentId.value = String(frontierData.session?.active_fragment_id || fromId)
      }
    }
    await api.streamTurn(
      workspace.activeProjectId,
      workspace.activeStory.story_id,
      String(route.params.sessionId),
      { user_message: message, action_type: actionType },
      (event, data) => {
        if (event === 'operation.started' && data?.operation_id) operationId.value = String(data.operation_id)
        if (event === 'delta') streamingText.value += String(data?.text || '')
        if (event === 'cancelled') cancelledByUser.value = true
        if (event === 'error') throw new ApiClientError(String(data?.message || '生成失败'), 500, String(data?.code || 'workflow_failed'))
      },
    )
    if (!cancelledByUser.value) {
      const data = await api.session(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId))
      turns.value = data.turns
      fragments.value = data.fragments
    } else {
      error.value = '已停止本轮生成'
    }
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '本轮生成失败'
  } finally {
    sending.value = false
    cancelling.value = false
    operationId.value = ''
    streamingText.value = ''
  }
}

async function cancelGeneration() {
  if (!operationId.value || cancelling.value) return
  cancelling.value = true
  try {
    await api.cancelOperation(operationId.value)
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '停止生成失败'
    cancelling.value = false
  }
}

async function confirmAndExtract(fragmentId: string) {
  if (!workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  try {
    await api.acceptFragment(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId), fragmentId)
    await reloadBundle()
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '确认片段失败'
    return
  }
  const fragment = fragments.value.find((item) => item.fragment_id === fragmentId)
  if (!fragment) return
  if (fragment.extraction_status === 'completed') {
    extractNotice.value = '片段已确认进正文。'
  } else if (extractingId.value !== fragmentId) {
    extractNotice.value = '片段已确认，正在提炼长期设定…'
    await extractFragment(fragmentId)
  }
}

async function extractFragment(fragmentId: string) {
  if (!workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId || extractingId.value) return
  extractingId.value = fragmentId
  extractNotice.value = ''
  extractBlocked.value = { ids: [], count: 0, sample: '' }
  let result: Record<string, any> | null = null
  const doneResult: { value: Record<string, any> | null } = { value: null }
  try {
    await api.streamFragmentExtraction(
      workspace.activeProjectId,
      workspace.activeStory.story_id,
      String(route.params.sessionId),
      fragmentId,
      (event, data) => {
        if (event === 'done' && data?.result) doneResult.value = data.result as Record<string, any>
        if (event === 'error') throw new ApiClientError(String(data?.message || '设定提炼失败'), 500, String(data?.code || 'extract_failed'))
      },
    )
    result = doneResult.value
    const autoConfirm = (result?.auto_confirm || {}) as Record<string, any>
    const confirmedIds = Array.isArray(autoConfirm.confirmed_ids) ? autoConfirm.confirmed_ids.map(String) : []
    const blockedIds = Array.isArray(autoConfirm.blocked_ids) ? autoConfirm.blocked_ids.map(String) : []
    const confirmedCount = confirmedIds.length
    const blockedCount = blockedIds.length
    const queuedCount = Number(result?.queued_count ?? 0)
    if (blockedCount) {
      const reasons = autoConfirm.blocked_reasons && typeof autoConfirm.blocked_reasons === 'object' ? (autoConfirm.blocked_reasons as Record<string, unknown>) : {}
      const samples = Object.values(reasons).slice(0, 2).map(String)
      extractBlocked.value = { ids: blockedIds, count: blockedCount, sample: samples.join('；') }
    }
    if (confirmedCount && !blockedCount) extractNotice.value = `已提炼 ${queuedCount || confirmedCount} 条设定，自动确认进入正式知识。`
    else if (confirmedCount && blockedCount) extractNotice.value = `已提炼 ${queuedCount || (confirmedCount + blockedCount)} 条：${confirmedCount} 条已确认，${blockedCount} 条与现有设定冲突或存疑。`
    else if (blockedCount) extractNotice.value = `已提炼 ${blockedCount} 条候选，均与现有设定冲突或存疑，留在待审核。`
    else if (queuedCount) extractNotice.value = `已提炼 ${queuedCount} 条设定候选。`
    else extractNotice.value = '这段内容没有提炼出新的长期设定。'
    await reloadBundle()
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '设定提炼失败'
  } finally {
    extractingId.value = ''
  }
}

async function adoptBlockedExtractions() {
  if (!extractBlocked.value.ids.length || !workspace.activeProjectId) return
  try {
    await api.confirmPending(workspace.activeProjectId, extractBlocked.value.ids)
    extractBlocked.value = { ids: [], count: 0, sample: '' }
    extractNotice.value = '已采纳冲突候选进入正式知识；请到知识库核对是否与旧设定并存。'
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '采纳设定失败'
  }
}

function goReviewPending() {
  if (!workspace.activeProjectId) return
  void router.push({ name: 'conversational-library' })
}

async function addAttachment() {
  if (!attachmentText.value.trim() || !workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  attachmentSaving.value = true
  try {
    const data = await api.addPastedAttachment(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId), attachmentText.value.trim(), attachmentTitle.value || '粘贴资料')
    attachments.value.push(data.attachment)
    attachmentText.value = ''
    attachmentOpen.value = false
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '资料添加失败' } finally { attachmentSaving.value = false }
}

async function addUrlAttachment() {
  if (!attachmentUrl.value.trim() || !workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  attachmentSaving.value = true
  try { const data = await api.addUrlAttachment(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId), attachmentUrl.value.trim()); attachments.value.push(data.attachment); attachmentUrl.value = ''; attachmentOpen.value = false } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '网页资料添加失败' } finally { attachmentSaving.value = false }
}

async function addFileAttachment(event: Event) {
  const files = Array.from((event.target as HTMLInputElement).files || [])
  if (!files.length || !workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  attachmentSaving.value = true
  batchUploadMessage.value = `正在导入 ${files.length} 个文件…`
  let imported = 0
  try {
    for (const file of files) {
      const data = await api.addFileAttachment(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId), file)
      if (data.attachment) { attachments.value.push(data.attachment); imported += 1 }
    }
    batchUploadMessage.value = `已加入 ${imported} 个文件，解析和知识化将在后台继续。`
    attachmentFile.value = null
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '批量文件资料添加失败'; batchUploadMessage.value = `已加入 ${imported}/${files.length} 个文件` } finally { attachmentSaving.value = false }
}

async function retryAttachment(attachment: any) {
  if (!workspace.activeProjectId || !attachment.ingestion_task_id) return
  try {
    await api.controlIngestionTask(workspace.activeProjectId, String(attachment.ingestion_task_id), 'retry')
    await reloadBundle()
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '资料任务重试失败' }
}

async function loadContextPreview() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  contextLoading.value = true
  try { contextData.value = await api.contextPreview(workspace.activeProjectId, workspace.activeStory.story_id, draft.value.trim(), undefined, 24000); contextOpen.value = true }
  catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '上下文预览失败' }
  finally { contextLoading.value = false }
}

async function renameSession() {
  if (!workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  const title = await dialog.prompt({ title: '重命名会话', confirmLabel: '保存', input: { label: '会话名称', initialValue: sessionTitle.value || '未命名会话' } })
  if (!title?.trim()) return
  try { const data = await api.renameSession(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId), title.trim()); sessionTitle.value = data.session.title } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '重命名失败' }
}

function fragmentStatusLabel(status: string) {
  return ({ proposed: '候选', accepted: '已采用', rejected: '未采用', superseded: '已替换' } as Record<string, string>)[status] || status
}

function actionStatusLabel(status: string) {
  return ({ planned: '待确认', awaiting_confirmation: '待确认', running: '执行中', completed: '已完成', cancelled: '已取消', failed: '失败', undone: '已撤销' } as Record<string, string>)[status] || status
}

function actionTypeLabel(type: string) {
  return ({ update_config: '更新配置', save_chapter: '保存章节', refine_knowledge: '提炼知识', update_knowledge: '更新知识', update_context: '更新上下文' } as Record<string, string>)[type] || type
}

async function planActionFromDraft() {
  if (!draft.value.trim() || !workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  try {
    const data = await api.planAction(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId), draft.value.trim())
    actions.value = [data.action, ...actions.value.filter((item) => item.action_id !== data.action.action_id)]
    draft.value = ''
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '动作规划失败' }
}

async function executeAction(action: CreativeAction) {
  if (!workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  try {
    const data = await api.executeAction(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId), action.action_id, true)
    actions.value = actions.value.map((item) => item.action_id === data.action.action_id ? data.action : item)
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '动作执行失败' }
}

async function cancelAction(action: CreativeAction) {
  if (!workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  try { const data = await api.cancelAction(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId), action.action_id); actions.value = actions.value.map((item) => item.action_id === data.action.action_id ? data.action : item) } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '动作取消失败' }
}

async function undoAction(action: CreativeAction) {
  if (!workspace.activeProjectId || !workspace.activeStory || !route.params.sessionId) return
  try { const data = await api.undoAction(workspace.activeProjectId, workspace.activeStory.story_id, String(route.params.sessionId), action.action_id); actions.value = [data.action, ...actions.value.map((item) => item.action_id === action.action_id ? { ...item, status: 'undone' } : item)] } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '动作撤销失败' }
}
</script>

<template>
  <div class="session-tools">
    <aside v-if="contextOpen" class="context-panel"><div class="context-panel-head"><strong>本轮上下文检查</strong><button class="session-rename" @click="contextOpen = false">关闭</button></div><p v-if="contextData?.summary" class="context-summary">{{ contextData.summary }}</p><div class="context-metrics"><span>预算 <b>{{ contextData?.budget || 24000 }}</b></span><span>估算 <b>{{ contextData?.estimated_tokens || contextData?.token_count || '—' }}</b></span><span>来源 <b>{{ contextData?.sources?.length || contextData?.evidence?.length || 0 }}</b></span></div><details v-if="contextData" class="context-details"><summary>查看技术明细</summary><pre class="context-json">{{ JSON.stringify(contextData, null, 2) }}</pre></details></aside>
    <button class="context-toggle" :disabled="contextLoading" @click="loadContextPreview">{{ contextLoading ? '检查中…' : '检查上下文' }}</button>
    <div v-if="attachments.length" class="attachment-progress-panel"><span v-for="attachment in attachments" :key="`progress-${attachment.attachment_id}`" class="attachment-progress-item"><strong>{{ attachment.title || attachment.filename }}</strong><small>{{ attachment.task_status || attachment.status || '已索引' }}<template v-if="attachment.task_progress?.total"> · {{ attachment.task_progress.completed || 0 }}/{{ attachment.task_progress.total }}</template></small><button v-if="attachment.task_status === 'failed' || attachment.status === 'failed'" class="retry-chip" @click="retryAttachment(attachment)">重试</button></span></div>
    <aside v-if="fragments.length" class="fragment-timeline"><strong>版本记录</strong><span v-for="(fragment, index) in fragments" :key="`timeline-${fragment.fragment_id}`"><i :class="{ active: fragment.status === 'accepted' }"></i>V{{ index + 1 }} · {{ fragmentStatusLabel(fragment.status) }} · {{ fragment.created_at }}</span></aside>
  </div>
  <section class="session-page"><div class="session-title"><p class="eyebrow">当前会话</p><h1>{{ sessionTitle || workspace.activeStory?.name }}</h1><span class="pill">会话 {{ String(route.params.sessionId).slice(-8) }}</span><button class="session-rename" @click="renameSession">重命名</button></div><div v-if="loading" class="session-state">正在读取会话…</div><div v-else-if="error && !turns.length" class="session-state error">{{ error }}</div><div v-else class="session-content"><div v-if="actions.length" class="action-list"><p class="eyebrow">待确认操作</p><article v-for="action in actions" :key="action.action_id" class="action-card"><div><strong>{{ actionTypeLabel(action.action_type) }}</strong><span class="action-status">{{ actionStatusLabel(action.status) }}</span><p>{{ action.plan?.message || action.error_text || '等待处理' }}</p></div><div class="action-buttons"><button v-if="action.status === 'awaiting_confirmation' || action.status === 'planned'" class="button secondary" @click="executeAction(action)">确认执行</button><button v-if="action.status === 'awaiting_confirmation'" class="button ghost" @click="cancelAction(action)">取消</button><button v-if="action.status === 'completed' && action.result" class="button ghost" @click="undoAction(action)">撤销</button></div></article></div><div v-if="!turns.length && !fragments.length" class="session-state">会话尚无内容。可在下方输入写作要求或待讨论的问题。</div><template v-for="entry in timelineItems" :key="`${entry.kind}-${entry.id}`"><div v-if="entry.kind === 'turn'" class="turn-row"><span class="turn-dot"></span><div><small>你 · {{ entry.item.created_at }}</small><p>{{ entry.item.user_message }}</p></div></div><div v-else class="fragment-card"><small>NovelForge · {{ fragmentStatusLabel(entry.item.status) }}</small><p>{{ entry.item.content }}</p><div v-if="entry.item.status === 'proposed'" class="fragment-actions"><button class="button secondary" :disabled="extractingId === entry.item.fragment_id" @click="confirmAndExtract(entry.item.fragment_id)">{{ extractingId === entry.item.fragment_id ? '确认并提炼中…' : '确认并提炼' }}</button><span class="muted">草稿 · 直接发消息可继续修订</span></div><div v-else-if="entry.item.status === 'accepted' || entry.item.status === 'finalized'" class="fragment-actions"><template v-if="entry.item.extraction_status === 'completed'"><span class="extracted-state">已提炼进知识库</span></template><template v-else-if="extractingId === entry.item.fragment_id"><span class="extracting-state">正在提炼…</span></template><template v-else><button class="button ghost" @click="extractFragment(entry.item.fragment_id)">{{ entry.item.extraction_status === 'failed' ? '重试提炼' : '提炼设定' }}</button><span class="muted">认可这段文字后可提炼为长期设定</span></template></div></div></template><div v-if="streamingText" class="fragment-card streaming"><small>NovelForge · 正在生成</small><p>{{ streamingText }}<span class="cursor">▌</span></p></div><div v-if="attachments.length" class="attachment-list"><span v-for="attachment in attachments" :key="attachment.attachment_id">📎 {{ attachment.title || attachment.filename }}</span></div></div><p v-if="error" class="inline-error">{{ error }}</p><p v-if="extractNotice" class="extract-notice" role="status">{{ extractNotice }}</p><div v-if="extractBlocked.count" class="extract-conflict" role="alert"><p>{{ extractBlocked.count }} 条候选与现有设定冲突或存疑（{{ extractBlocked.sample }}），仍在待审核、未进入正式知识。</p><div class="extract-conflict-actions"><button class="button ghost" @click="adoptBlockedExtractions">采纳这些设定</button><button class="button ghost" @click="goReviewPending">去待审核处理</button></div></div><div v-if="attachmentOpen" class="attachment-tray"><input v-model="attachmentTitle" placeholder="资料标题" /><textarea v-model="attachmentText" rows="4" placeholder="粘贴资料；默认仅用于当前会话"></textarea><input v-model="attachmentUrl" type="url" placeholder="或输入公开网页 URL" /><input ref="attachmentFile" type="file" accept=".txt,.md,.pdf,.docx,.epub" multiple @change="addFileAttachment" /><small v-if="batchUploadMessage" class="batch-upload-message">{{ batchUploadMessage }}</small><div><button class="button secondary" :disabled="attachmentSaving || !attachmentText.trim()" @click="addAttachment">{{ attachmentSaving ? '保存中…' : '添加文本资料' }}</button><button class="button secondary" :disabled="attachmentSaving || !attachmentUrl.trim()" @click="addUrlAttachment">{{ attachmentSaving ? '抓取中…' : '添加网页' }}</button><button class="button ghost" @click="attachmentOpen = false">关闭</button></div></div><div class="session-composer"><span class="composer-mode-hint"><template v-if="!activeDraft && hasConfirmedText">从 <select v-model="startFromId" class="start-select" aria-label="生成起点" :disabled="sending"><option v-for="option in confirmedStarts" :key="option.fragment_id" :value="option.fragment_id">V{{ option.vNo }} · {{ option.short }}</option></select> 之后继续生成</template><template v-else>{{ composerModeHint }}</template></span><textarea v-model="draft" rows="2" aria-label="写作要求" placeholder="输入写作要求、修改意见或下一段内容" :disabled="sending" @compositionstart="composing = true" @compositionend="composing = false" @keydown.meta.enter.prevent="!composing && send()" @keydown.ctrl.enter.prevent="!composing && send()"></textarea><button class="attach-button" title="添加会话资料" @click="attachmentOpen = !attachmentOpen">＋资料</button><button class="attach-button" title="将当前输入识别为需要确认的操作" :disabled="!draft.trim()" @click="planActionFromDraft">识别操作</button><button v-if="sending" class="attach-button" :disabled="cancelling || !operationId" @click="cancelGeneration">{{ cancelling ? '停止中…' : '停止生成' }}</button><button class="button accent" :disabled="sending || !draft.trim()" @click="send">{{ sending ? '生成中…' : '发送' }}</button></div></section>
</template>

<style scoped>
.session-page { max-width: 820px; margin: clamp(34px, 8vh, 80px) auto 0; padding: 0 25px 60px; }.session-title { display: flex; align-items: center; gap: 13px; flex-wrap: wrap; }.session-title h1 { flex-basis: 100%; margin: 7px 0 0; color: #f0ebe4; font-family: Georgia, serif; font-size: clamp(35px, 5vw, 53px); font-weight: 400; letter-spacing: -.05em; }.session-title .pill { color: #aea79d; background: rgba(255,255,255,.07); }.session-content { min-height: 350px; margin-top: 42px; }.session-state { display: grid; min-height: 250px; place-items: center; color: var(--muted); font-size: 13px; text-align: center; }.session-state.error, .inline-error { color: #de9d84; }.inline-error { margin: 16px 0 0; font-size: 12px; }.turn-row { display: flex; gap: 14px; margin: 25px 0; }.turn-dot { flex: 0 0 7px; width: 7px; height: 7px; margin-top: 8px; border-radius: 50%; background: #d19372; }.turn-row small, .fragment-card small { color: var(--muted); font-size: 11px; }.turn-row p { margin: 7px 0 0; color: #d8d4cc; font-size: 15px; line-height: 1.8; }.fragment-card { margin: 27px 0; padding: 21px 24px; border: 1px solid rgba(222,172,139,.2); border-radius: 15px; color: #e6ded5; background: rgba(182,116,83,.1); }.fragment-card.streaming { border-color: rgba(222,172,139,.42); }.fragment-card p { margin: 10px 0 0; font-family: Georgia, serif; font-size: 17px; line-height: 1.9; }.fragment-actions { display: flex; align-items: center; gap: 12px; margin-top: 15px; }.fragment-actions .button { padding: 8px 13px; font-size: 12px; }.cursor { color: #d19372; animation: blink 1s steps(2, start) infinite; }.session-composer { display: flex; align-items: flex-end; gap: 12px; margin-top: 20px; padding: 13px 13px 13px 18px; border: 1px solid rgba(255,255,255,.13); border-radius: 15px; background: #363936; }.session-composer textarea { flex: 1; resize: none; border: 0; outline: 0; color: #e8e2da; background: transparent; line-height: 1.6; }.session-composer textarea::placeholder { color: var(--muted); }.session-composer textarea:disabled { opacity: .6; } @keyframes blink { 50% { opacity: 0; } }
.context-toggle { display: block; margin: 20px 0 0 auto; padding: 6px 9px; border: 1px solid rgba(255,255,255,.13); border-radius: 7px; color: #b9aa9c; background: transparent; cursor: pointer; font-size: 10px; }.context-toggle:hover { color: #efd1bb; border-color: rgba(222,172,139,.4); }.context-panel { margin: 14px 0; padding: 15px; border: 1px solid rgba(222,172,139,.22); border-radius: 12px; background: rgba(0,0,0,.14); }.context-panel-head { display: flex; align-items: center; justify-content: space-between; color: #dfc0a9; font-size: 12px; }.context-summary { margin: 10px 0; color: var(--muted); font-size: 11px; line-height: 1.6; }.context-metrics { display: flex; flex-wrap: wrap; gap: 15px; color: var(--muted); font-size: 10px; }.context-metrics b { color: #dfc0a9; font-weight: 500; }.context-json { max-height: 180px; margin: 12px 0 0; overflow: auto; color: var(--muted); font-size: 10px; line-height: 1.5; white-space: pre-wrap; }
.session-tools { max-width: 820px; margin: 0 auto; padding: 0 25px; }.context-details { margin-top: 12px; color: var(--muted); font-size: 10px; }.context-details summary { cursor: pointer; }.context-details[open] summary { color: #c5b5a6; }
</style>

<style scoped>
.fragment-actions .ghost { padding: 8px 9px; border: 1px solid rgba(255,255,255,.15); color: #b4aaa0; background: transparent; font-size: 12px; }
.fragment-actions .ghost:hover { color: #f0d8c4; border-color: rgba(222,172,139,.45); }
.fragment-actions .ghost:disabled { cursor: not-allowed; opacity: .5; }
.extracted-state { color: #7da477; font-size: 11px; }
.extracting-state { color: #e0a17d; font-size: 11px; }
.extract-notice { margin: 12px 0; padding: 9px 12px; border: 1px solid rgba(222,172,139,.3); border-radius: 9px; color: #d8c2ae; background: rgba(190,111,78,.1); font-size: 11px; }.composer-mode-hint { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; flex: 0 0 100%; padding: 2px 2px 10px; margin-bottom: 9px; border-bottom: 1px solid rgba(255,255,255,.08); color: #979c93; font-size: 11px; letter-spacing: .03em; }
.start-select { max-width: 300px; padding: 4px 6px; border: 1px solid rgba(255,255,255,.14); border-radius: 7px; outline: 0; color: #d8c2ae; background: #292b2a; font-family: inherit; font-size: 11px; }
.session-composer { flex-wrap: wrap; }
.extract-conflict { margin: 10px 0 0; padding: 10px 12px; border: 1px solid rgba(231,146,120,.4); border-radius: 9px; background: rgba(160,60,50,.12); }
.extract-conflict p { margin: 0 0 8px; color: #e5b3a2; font-size: 11px; line-height: 1.6; }
.extract-conflict-actions { display: flex; gap: 8px; }
.extract-conflict-actions .button { padding: 6px 10px; font-size: 11px; }
.session-rename { padding: 5px 9px; border: 1px solid rgba(255,255,255,.13); border-radius: 7px; color: #9e9a92; background: transparent; cursor: pointer; font-size: 10px; }.session-rename:hover { color: #ead0bc; }
.action-list { display: grid; gap: 9px; margin: 0 0 22px; }.action-card { display: flex; justify-content: space-between; gap: 14px; padding: 15px 17px; border: 1px solid rgba(222,172,139,.24); border-radius: 12px; background: rgba(190,111,78,.09); }.action-card strong { color: #e8c4ad; font-size: 12px; }.action-status { margin-left: 9px; color: var(--muted); font-size: 10px; }.action-card p { margin: 7px 0 0; color: var(--muted); font-size: 12px; line-height: 1.6; }.action-buttons { display: flex; flex-shrink: 0; align-items: center; gap: 5px; }.action-buttons .button { padding: 7px 9px; font-size: 10px; }
.session-composer select { padding: 9px 6px; border: 0; border-right: 1px solid rgba(255,255,255,.1); outline: 0; color: #bcae9f; background: transparent; font-size: 11px; }
.attach-button { padding: 8px 9px; border: 1px solid rgba(255,255,255,.12); border-radius: 8px; color: #b9aa9c; background: transparent; cursor: pointer; font-size: 11px; }.attach-button:hover { color: #efd1bb; border-color: rgba(222,172,139,.4); }.attachment-tray { display: grid; gap: 8px; margin-bottom: 10px; padding: 15px; border: 1px solid rgba(222,172,139,.2); border-radius: 12px; background: rgba(0,0,0,.12); }.attachment-tray input, .attachment-tray textarea { padding: 9px; border: 1px solid rgba(255,255,255,.12); border-radius: 8px; outline: 0; color: #e8e2da; background: transparent; font: inherit; font-size: 12px; }.attachment-tray textarea { resize: vertical; line-height: 1.6; }.attachment-tray .ghost { margin-left: 6px; }.attachment-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 16px 0; }.attachment-list span { padding: 5px 8px; border: 1px solid rgba(255,255,255,.1); border-radius: 99px; color: var(--muted); font-size: 10px; }
.attachment-progress-panel { display: grid; gap: 6px; margin: 12px 0; }.attachment-progress-item { display: flex; align-items: center; gap: 9px; padding: 7px 9px; border: 1px solid rgba(255,255,255,.08); border-radius: 8px; color: var(--muted); font-size: 10px; }.attachment-progress-item strong { color: #c4bdb4; font-weight: 500; }.attachment-progress-item small { color: var(--muted); }.retry-chip { padding: 2px 6px; border: 1px solid rgba(222,172,139,.3); border-radius: 6px; color: #e0ae91; background: transparent; cursor: pointer; font-size: 10px; }
.batch-upload-message { color: #8fae89; font-size: 10px; }
.fragment-timeline { display: grid; gap: 6px; margin: 14px 0; padding: 11px 13px; border-left: 2px solid rgba(222,172,139,.28); color: var(--muted); font-size: 10px; }.fragment-timeline strong { color: #c4bdb4; font-size: 11px; }.fragment-timeline span { display: flex; align-items: center; gap: 7px; }.fragment-timeline i { width: 6px; height: 6px; border-radius: 50%; background: #777d75; }.fragment-timeline i.active { background: #7da477; }
@media (max-width: 620px) { .session-composer { align-items: stretch; flex-wrap: wrap; }.session-composer select { width: 100%; border-right: 0; border-bottom: 1px solid rgba(255,255,255,.1); }.session-composer textarea { flex-basis: 100%; } }
</style>
