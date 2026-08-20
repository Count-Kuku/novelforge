<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'

const workspace = useWorkspaceStore()
const topic = ref('')
const objective = ref('')
const scope = ref<'reference' | 'canon' | 'project'>('reference')
const submitting = ref(false)
const message = ref('')
const tasks = ref<any[]>([])
const sources = ref<any[]>([])
const selectedTask = ref<any | null>(null)
const selectedClaimIds = ref<string[]>([])
const workbench = ref<Record<string, any>>({})
const batchFiles = ref<File[]>([])
const batchUploading = ref(false)
const batchMessage = ref('')
const useOcr = ref(false)
const ocrPreviewLoading = ref(false)
const ocrPreview = ref<any | null>(null)

async function load() {
  if (!workspace.activeProjectId) return
  const [taskData, sourceData, workbenchData] = await Promise.all([api.tasks(workspace.activeProjectId), api.sources(workspace.activeProjectId), api.ingestionWorkbench(workspace.activeProjectId)])
  tasks.value = taskData.web_research as any[]
  sources.value = sourceData.sources as any[]
  workbench.value = workbenchData as any
}

async function reviewClaims() {
  if (!workspace.activeProjectId || !selectedTask.value || !selectedClaimIds.value.length) return
  try { const data = await api.reviewResearchClaims(workspace.activeProjectId, String(selectedTask.value.task_id), selectedClaimIds.value); selectedTask.value = data.task; message.value = `已送审 ${data.result.queued_count || selectedClaimIds.value.length} 条研究结论`; selectedClaimIds.value = []; await load() } catch (reason) { message.value = reason instanceof ApiClientError ? reason.message : '研究结论送审失败' }
}

function toggleClaim(claimId: string) {
  selectedClaimIds.value = selectedClaimIds.value.includes(claimId) ? selectedClaimIds.value.filter((id) => id !== claimId) : [...selectedClaimIds.value, claimId]
}

async function openTask(task: any) {
  selectedClaimIds.value = []
  if (!workspace.activeProjectId) return
  try { selectedTask.value = (await api.researchTask(workspace.activeProjectId, String(task.task_id))).task } catch { selectedTask.value = task }
}

async function submit() {
  if (!workspace.activeProjectId || !topic.value.trim() || submitting.value) return
  submitting.value = true
  message.value = ''
  try { await api.createResearchTask(workspace.activeProjectId, { topic: topic.value.trim(), objective: objective.value.trim(), scope: scope.value, story_id: workspace.activeStory?.story_id || '' }); topic.value = ''; objective.value = ''; message.value = '研究任务已加入队列'; await load() } catch (reason) { message.value = reason instanceof ApiClientError ? reason.message : '创建研究任务失败' } finally { submitting.value = false }
}

async function controlTask(task: any, action: 'pause' | 'resume' | 'cancel' | 'retry') {
  if (!workspace.activeProjectId) return
  try {
    const data = await api.controlResearchTask(workspace.activeProjectId, String(task.task_id), action)
    const index = tasks.value.findIndex((item) => item.task_id === task.task_id)
    if (index >= 0) tasks.value[index] = data.task
    message.value = action === 'pause' ? '任务已暂停' : action === 'resume' ? '任务已继续' : action === 'retry' ? '任务已重新排队' : '任务已取消'
  } catch (reason) { message.value = reason instanceof ApiClientError ? reason.message : '任务控制失败' }
}

async function activateSources(task: any) {
  if (!workspace.activeProjectId) return
  try {
    const data = await api.activateResearchSources(workspace.activeProjectId, String(task.task_id))
    const index = tasks.value.findIndex((item) => item.task_id === task.task_id)
    if (index >= 0) tasks.value[index] = data.task
    message.value = `已激活 ${data.result.source_count || data.result.changed_count || 0} 个网页来源`
    await load()
  } catch (reason) { message.value = reason instanceof ApiClientError ? reason.message : '来源激活失败' }
}

function selectBatchFiles(event: Event) {
  batchFiles.value = Array.from((event.target as HTMLInputElement).files || [])
  ocrPreview.value = null
  batchMessage.value = batchFiles.value.length ? `已选择 ${batchFiles.value.length} 个文件` : ''
}

async function previewSelectedOcr() {
  const pdf = batchFiles.value.find((file) => file.name.toLowerCase().endsWith('.pdf'))
  if (!workspace.activeProjectId || !workspace.activeStory?.story_id || !pdf || ocrPreviewLoading.value) return
  ocrPreviewLoading.value = true
  try {
    ocrPreview.value = await api.previewOcr(workspace.activeProjectId, workspace.activeStory.story_id, pdf)
    batchMessage.value = `OCR 预览完成：${ocrPreview.value.metadata?.page_count || 0} 页`
  } catch (reason) { batchMessage.value = reason instanceof ApiClientError ? reason.message : 'OCR 预览失败' } finally { ocrPreviewLoading.value = false }
}

async function uploadBatch() {
  if (!workspace.activeProjectId || !workspace.activeStory?.story_id || !batchFiles.value.length || batchUploading.value) return
  batchUploading.value = true
  try {
    const data = await api.uploadIngestionBatch(workspace.activeProjectId, workspace.activeStory.story_id, batchFiles.value, 'project', useOcr.value)
    batchMessage.value = `已加入 ${data.accepted_count} 个文件；后台会继续解析${data.ocr_requested ? '、保存 OCR 页级证据' : ''}和知识化。${data.warnings.length ? ` 警告 ${data.warnings.length} 条。` : ''}`
    batchFiles.value = []
    ocrPreview.value = null
    await load()
  } catch (reason) { batchMessage.value = reason instanceof ApiClientError ? reason.message : '批量导入失败' } finally { batchUploading.value = false }
}

onMounted(load)
</script>

<template>
<section class="research-page"><div class="research-heading"><div><p class="eyebrow">WEB RESEARCH</p><h1>把外部资料带回来，<em>但先经过审核。</em></h1><p>搜索、抓取、提取和激活是分开的步骤；未经人工确认的网页不会自动进入正式知识。</p></div><button class="button secondary" @click="load">刷新任务</button></div><article class="research-form"><p class="eyebrow">NEW RESEARCH TASK</p><div class="form-grid"><label>主题<input v-model="topic" placeholder="例如：某种历史制度的公开资料" /></label><label>范围<select v-model="scope"><option value="reference">参考资料</option><option value="canon">世界观依据</option><option value="project">项目资料</option></select></label><label class="wide">目标<textarea v-model="objective" rows="3" placeholder="希望研究回答什么问题？"></textarea></label></div><div class="form-footer"><span v-if="message">{{ message }}</span><button class="button accent" :disabled="submitting || !topic.trim()" @click="submit">{{ submitting ? '提交中…' : '创建研究任务' }}</button></div></article><article class="batch-import-card"><div><p class="eyebrow">BATCH IMPORT</p><h2>一次整理多份资料</h2><p class="muted">最多 20 个文件、总计 32MB；原文先进入来源账本，解析、OCR 与知识化在后台继续。</p></div><input type="file" multiple accept=".txt,.md,.pdf,.docx,.epub" @change="selectBatchFiles" /><label class="ocr-toggle"><input v-model="useOcr" type="checkbox" /> 对 PDF 启用本地 OCR <small>仅在本机识别；会保留页级置信度。</small></label><div class="batch-import-actions"><span v-if="batchMessage">{{ batchMessage }}</span><div class="batch-buttons"><button class="button secondary" :disabled="ocrPreviewLoading || !batchFiles.some((file) => file.name.toLowerCase().endsWith('.pdf'))" @click="previewSelectedOcr">{{ ocrPreviewLoading ? '预览中…' : '预览 OCR' }}</button><button class="button accent" :disabled="batchUploading || !batchFiles.length" @click="uploadBatch">{{ batchUploading ? '批量导入中…' : '确认导入' }}</button></div></div></article><article v-if="ocrPreview" class="ocr-preview-card"><div><p class="eyebrow">OCR PREVIEW</p><h2>{{ ocrPreview.filename }}</h2><p class="muted">{{ ocrPreview.metadata?.page_count || 0 }} 页 · 仅预览，不会写入资料库；置信度低的页面需人工抽查。</p></div><div v-for="section in ocrPreview.sections" :key="`${section.page}-${section.title}`" class="ocr-preview-row"><div><strong>第 {{ section.page }} 页 · {{ section.confidence }}%</strong><small>{{ section.char_count }} 字</small></div><p>{{ section.text_preview || '没有识别到文本。' }}</p></div><p v-for="warning in ocrPreview.warnings" :key="warning" class="ocr-warning">{{ warning }}</p></article><div class="research-columns"><article><p class="eyebrow">DURABLE TASKS · {{ tasks.length }}</p><div v-if="!tasks.length" class="muted">还没有网络研究任务。</div><div v-for="task in tasks" :key="task.task_id" class="task-row" @click="openTask(task)"><div class="task-main"><strong>{{ task.topic || task.title || '未命名研究' }}</strong><small>{{ task.status || 'queued' }} · {{ task.task_id }}</small><div class="progress-track"><i :style="{ width: `${Math.min(100, Number(task.progress?.percent || (task.progress?.total ? (Number(task.progress.completed || 0) / Number(task.progress.total)) * 100 : 0)))}%` }"></i></div></div><div class="task-side"><span>{{ task.progress?.completed || 0 }}/{{ task.progress?.total || '—' }}</span><div class="task-actions"><button v-if="task.status === 'running' || task.status === 'queued'" class="link-button" @click.stop="controlTask(task, 'pause')">暂停</button><button v-if="task.status === 'paused'" class="link-button" @click.stop="controlTask(task, 'resume')">继续</button><button v-if="task.status === 'failed' || task.status === 'completed_with_errors'" class="link-button" @click.stop="controlTask(task, 'retry')">重试</button><button v-if="task.status === 'completed' || task.status === 'completed_with_errors'" class="link-button" @click.stop="activateSources(task)">激活来源</button><button v-if="!['completed','cancelled','failed'].includes(task.status)" class="link-button danger" @click.stop="controlTask(task, 'cancel')">取消</button></div></div></div></article><article><p class="eyebrow">SOURCE LEDGER · {{ sources.length }}</p><div v-if="!sources.length" class="muted">来源账本为空。</div><div v-for="source in sources.slice(0, 12)" :key="source.source_id || source.relative_path" class="source-row"><strong>{{ source.title || source.source_name || source.relative_path }}</strong><small>{{ source.status || source.retrieval_status || '已登记' }}</small></div></article></div><article v-if="selectedTask" class="claims-panel"><p class="eyebrow">CLAIM REVIEW</p><h2>{{ selectedTask.topic || selectedTask.title }}</h2><p class="muted">选择已验证结论，送入待审核知识；不会直接写入正式知识。</p><div v-for="claim in (selectedTask.result?.verified_claims || [])" :key="claim.claim_id" class="claim-row"><label><input type="checkbox" :checked="selectedClaimIds.includes(String(claim.claim_id))" @change="toggleClaim(String(claim.claim_id))" /><span><strong>{{ claim.summary || claim.claim || '研究结论' }}</strong><small>{{ claim.authority || 'unknown' }} · 证据 {{ claim.evidence_count || claim.evidence?.length || 0 }}</small></span></label></div><button class="button accent" :disabled="!selectedClaimIds.length" @click="reviewClaims">送入待审核知识（{{ selectedClaimIds.length }}）</button></article><article class="ingestion-card"><div><p class="eyebrow">INGESTION WORKBENCH</p><h2>资料批次健康</h2><p class="muted">原文可读性、知识化进度和失败片段分开呈现，后台任务可安全恢复。</p></div><div class="workbench-stats"><span>批次 {{ (workbench.batch_rows || []).length }}</span><span>未完成 {{ workbench.unfinished_batch_count || 0 }}</span><span>失败任务 {{ workbench.failed_task_count || 0 }}</span><span>活动任务 {{ workbench.active_task_count || 0 }}</span></div><div v-for="row in (workbench.batch_rows || []).slice(0, 6)" :key="row.batch_id" class="source-row"><strong>{{ row.title }}</strong><small>{{ row.status_label }} · {{ row.completed_count }}/{{ row.segment_count }}</small></div></article></section>
</template>

<style scoped>
.research-page { max-width: 1120px; margin: 0 auto; padding: 12px 0 60px; }.research-heading { display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 34px; }.research-heading h1 { max-width: 760px; margin: 10px 0 16px; font-family: Georgia, serif; font-size: clamp(36px, 5vw, 62px); font-weight: 400; letter-spacing: -.055em; line-height: 1.08; }.research-heading h1 em { color: var(--accent); font-style: normal; }.research-heading p:not(.eyebrow) { max-width: 600px; color: var(--muted); font-size: 13px; line-height: 1.8; }.research-form, .research-columns article { padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }.form-grid { display: grid; grid-template-columns: 1fr 220px; gap: 12px; margin-top: 17px; }.form-grid label { display: grid; gap: 6px; color: var(--muted); font-size: 11px; }.form-grid .wide { grid-column: 1 / -1; }.form-grid input, .form-grid select, .form-grid textarea { width: 100%; padding: 10px; border: 1px solid var(--line); border-radius: 8px; outline: 0; color: inherit; background: transparent; font: inherit; font-size: 12px; }.form-grid textarea { resize: vertical; line-height: 1.6; }.form-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 15px; color: #7da477; font-size: 11px; }.research-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }.task-row, .source-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; border-top: 1px solid var(--line); }.task-main { min-width: 0; flex: 1; }.task-row strong, .source-row strong { display: block; font-size: 12px; font-weight: 500; }.task-row small, .source-row small { display: block; margin-top: 4px; color: var(--muted); font-size: 10px; }.task-side { display: grid; justify-items: end; gap: 8px; color: var(--accent); font-size: 11px; }.task-actions { display: flex; flex-wrap: wrap; justify-content: end; gap: 7px; }.link-button { padding: 0; border: 0; color: var(--accent); background: transparent; cursor: pointer; font-size: 10px; }.link-button:hover { text-decoration: underline; }.link-button.danger { color: #d18d82; }.progress-track { height: 4px; margin-top: 9px; overflow: hidden; border-radius: 99px; background: rgba(255,255,255,.08); }.progress-track i { display: block; height: 100%; border-radius: inherit; background: var(--accent); transition: width .2s ease; }.muted { color: var(--muted); font-size: 12px; }.claims-panel, .ingestion-card { margin-top: 16px; padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }.claims-panel h2, .ingestion-card h2 { margin: 5px 0 8px; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.claim-row { padding: 12px 0; border-top: 1px solid var(--line); }.claim-row label { display: flex; align-items: flex-start; gap: 9px; cursor: pointer; }.claim-row strong, .claim-row small { display: block; }.claim-row strong { font-size: 12px; font-weight: 500; }.claim-row small { margin-top: 4px; color: var(--muted); font-size: 10px; }.workbench-stats { display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0 5px; color: var(--accent); font-size: 11px; }
.batch-import-card { display: grid; gap: 12px; margin-top: 16px; padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.04); }.batch-import-card h2 { margin: 5px 0 7px; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.batch-import-card input[type=file] { width: 100%; padding: 12px; border: 1px dashed var(--line); border-radius: 9px; color: var(--muted); font-size: 11px; }.batch-import-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #7da477; font-size: 11px; }
.ocr-toggle { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 11px; }.ocr-toggle small { color: var(--muted); font-size: 10px; }.batch-buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }.ocr-preview-card { display: grid; gap: 12px; margin-top: 16px; padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }.ocr-preview-card h2 { margin: 5px 0 4px; font-family: Georgia, serif; font-size: 23px; font-weight: 400; }.ocr-preview-row { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 16px; padding: 12px 0; border-top: 1px solid var(--line); }.ocr-preview-row strong, .ocr-preview-row small { display: block; }.ocr-preview-row strong { color: var(--accent); font-size: 12px; }.ocr-preview-row small { margin-top: 5px; color: var(--muted); font-size: 10px; }.ocr-preview-row p { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.65; white-space: pre-wrap; }.ocr-warning { margin: 0; color: #d18d82; font-size: 11px; }
@media (max-width: 700px) { .research-heading { align-items: flex-start; flex-direction: column; }.form-grid, .research-columns { grid-template-columns: 1fr; }.form-grid .wide { grid-column: auto; }.form-footer { align-items: flex-start; flex-direction: column; } }
</style>
