<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { api, ApiClientError } from '../api/client'

const props = withDefaults(defineProps<{
  projectId: string
  storyId: string
  sessionId?: string
  branchId?: string
  mode?: 'library' | 'session'
  compact?: boolean
}>(), { mode: 'library', compact: false })

const emit = defineEmits<{
  imported: [payload: { count: number; failedCount: number; warnings: string[]; attachments: any[] }]
}>()

const tab = ref<'text' | 'files'>('text')
const title = ref('粘贴资料')
const text = ref('')
const scope = ref<'story' | 'project'>('story')
const files = ref<File[]>([])
const submitting = ref(false)
const message = ref('')
const warning = ref('')
const useOcr = ref(false)
const ocrPreview = ref<any | null>(null)
const ocrPreviewLoading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const inputId = `material-file-${useId()}`

const isSession = computed(() => props.mode === 'session' && Boolean(props.sessionId))
const acceptedExtensions = '.txt,.md,.markdown,.pdf,.docx,.epub'
const maxFileBytes = 32 * 1024 * 1024
const maxBatchBytes = 128 * 1024 * 1024
const maxBatchFiles = 20
const selectedNames = computed(() => files.value.map((file) => file.name).join('、'))
const hasPdf = computed(() => files.value.some((file) => file.name.toLowerCase().endsWith('.pdf')))

function chooseFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files || [])
  const oversized = selected.find((file) => file.size > maxFileBytes)
  const totalBytes = selected.reduce((total, file) => total + file.size, 0)
  const selectionError = selected.length > maxBatchFiles
    ? `一次最多选择 ${maxBatchFiles} 个文件。`
    : oversized
      ? `${oversized.name} 超过 32MB 单文件限制。`
      : totalBytes > maxBatchBytes
        ? '所选文件总大小超过 128MB。'
        : ''
  if (selectionError) {
    files.value = []
    message.value = ''
    warning.value = selectionError
    ocrPreview.value = null
    input.value = ''
    return
  }
  files.value = selected
  message.value = files.value.length ? `已选择 ${files.value.length} 个文件，请点击“确认导入”。` : ''
  warning.value = ''
  ocrPreview.value = null
}

function resetForm() {
  text.value = ''
  title.value = '粘贴资料'
  files.value = []
  useOcr.value = false
  ocrPreview.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function previewSelectedOcr() {
  const pdf = files.value.find((file) => file.name.toLowerCase().endsWith('.pdf'))
  if (!pdf || isSession.value || ocrPreviewLoading.value) return
  ocrPreviewLoading.value = true
  try {
    ocrPreview.value = await api.previewOcr(props.projectId, props.storyId, pdf)
    message.value = `OCR 预览完成：${ocrPreview.value.metadata?.page_count || 0} 页`
  } catch (reason) {
    warning.value = reason instanceof ApiClientError ? reason.message : 'OCR 预览失败'
  } finally {
    ocrPreviewLoading.value = false
  }
}

async function submit() {
  if (submitting.value) return
  const tabSnapshot = tab.value
  const textSnapshot = text.value.trim()
  const titleSnapshot = title.value.trim() || '粘贴资料'
  const filesSnapshot = files.value.slice()
  const projectId = props.projectId
  const storyId = props.storyId
  const sessionId = props.sessionId
  const sessionMode = isSession.value
  const branchSnapshot = props.branchId || undefined
  const scopeSnapshot = sessionMode ? scope.value : 'project'
  const useOcrSnapshot = useOcr.value
  if (tabSnapshot === 'text' && !textSnapshot) return
  if (tabSnapshot === 'files' && !filesSnapshot.length) return

  submitting.value = true
  message.value = tabSnapshot === 'files'
    ? `正在上传并解析 ${filesSnapshot.length} 个文件…`
    : ''
  warning.value = ''
  const imported: any[] = []
  const warnings: string[] = []
  const remainingFiles: File[] = []
  let acceptedCount = 0
  try {
    if (tabSnapshot === 'text') {
      if (sessionMode) {
        const data = branchSnapshot
          ? await api.addPastedAttachment(projectId, storyId, sessionId!, textSnapshot, titleSnapshot, scopeSnapshot, branchSnapshot)
          : await api.addPastedAttachment(projectId, storyId, sessionId!, textSnapshot, titleSnapshot, scopeSnapshot)
        if (data.attachment) imported.push(data.attachment)
        acceptedCount = imported.length
      } else {
        const data = await api.addPastedIngestionText(projectId, storyId, textSnapshot, titleSnapshot, 'project')
        if (data.attachment) imported.push(data.attachment)
        warnings.push(...(data.warnings || []))
        acceptedCount = Number(data.accepted_count ?? imported.length)
      }
    } else if (sessionMode) {
      for (const file of filesSnapshot) {
        try {
          const data = branchSnapshot
            ? await api.addFileAttachment(projectId, storyId, sessionId!, file, scopeSnapshot, branchSnapshot)
            : await api.addFileAttachment(projectId, storyId, sessionId!, file, scopeSnapshot)
          if (data.attachment) imported.push(data.attachment)
          acceptedCount = imported.length
          warnings.push(...(data.warnings || []))
        } catch (reason) {
          remainingFiles.push(file)
          warnings.push(`${file.name}：${reason instanceof ApiClientError ? reason.message : reason instanceof Error ? reason.message : '导入失败'}`)
        }
      }
    } else {
      const data = await api.uploadIngestionBatch(projectId, storyId, filesSnapshot, 'project', useOcrSnapshot)
      imported.push(...(data.attachments || []))
      warnings.push(...(data.warnings || []))
      acceptedCount = Number(data.accepted_count ?? imported.length)
    }
    const sameTarget = props.projectId === projectId && props.storyId === storyId && props.sessionId === sessionId && (props.branchId || undefined) === branchSnapshot
    if (sameTarget) {
      if (remainingFiles.length) files.value = remainingFiles
      else resetForm()
      message.value = `已保存 ${acceptedCount} 项资料，知识将自动提炼；原文仅用于查证。`
      if (warnings.length) warning.value = warnings.join('；')
      emit('imported', { count: acceptedCount, failedCount: remainingFiles.length, warnings, attachments: imported })
    }
  } catch (reason) {
    message.value = reason instanceof ApiClientError ? reason.message : '资料导入失败，可检查后重试。'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="material-import" :class="{ compact }">
    <div class="material-head"><div><p class="eyebrow">{{ mode === 'library' ? '导入资料' : '会话资料' }}</p><h2>{{ mode === 'library' ? '粘贴资料或导入文件' : '把资料加入当前创作' }}</h2><p class="material-hint">保存资料后自动提炼知识，原文仅用于来源查证。</p></div><span class="scope-badge">{{ mode === 'library' ? '项目资料' : (scope === 'story' ? '当前故事' : '整个项目') }}</span></div>
    <div class="material-tabs" role="tablist" aria-label="资料类型"><button type="button" :disabled="submitting" :class="{ active: tab === 'text' }" @click="tab = 'text'">粘贴资料</button><button type="button" :disabled="submitting" :class="{ active: tab === 'files' }" @click="tab = 'files'">导入文件</button></div>
    <label v-if="tab === 'text'" class="material-field">资料标题<input v-model="title" :disabled="submitting" maxlength="200" placeholder="例如：人物设定摘录" /></label>
    <textarea v-if="tab === 'text'" v-model="text" class="material-text" :disabled="submitting" rows="7" placeholder="粘贴需要长期参考的资料…"></textarea>
    <div v-else class="file-picker"><input :id="inputId" ref="fileInput" type="file" multiple :accept="acceptedExtensions" aria-label="选择资料文件" :disabled="submitting" @change="chooseFiles" /><label :for="inputId" class="file-picker-label"><strong>{{ files.length ? `已选择 ${files.length} 个文件` : '选择一个或多个资料文件' }}</strong><small>TXT、Markdown、DOCX、EPUB、PDF；选择后仍需确认导入</small></label><p v-if="selectedNames" class="file-names">{{ selectedNames }}</p></div>
    <div v-if="mode === 'session'" class="material-options"><label>保存范围<select v-model="scope" :disabled="submitting"><option value="story">当前故事（推荐）</option><option value="project">整个项目</option></select></label><small>资料不再保存为临时会话范围；后续会话和知识检索可按此范围使用。</small></div>
    <div v-if="mode === 'library' && tab === 'files'" class="ocr-options"><label><input v-model="useOcr" type="checkbox" :disabled="submitting || !hasPdf" /> 对 PDF 使用本地 OCR</label><button type="button" class="link-button" :disabled="submitting || ocrPreviewLoading || !hasPdf" @click="previewSelectedOcr">{{ ocrPreviewLoading ? '预览中…' : '预览 OCR' }}</button><small>仅用于扫描版 PDF；预览不会保存资料。</small></div>
    <article v-if="ocrPreview" class="ocr-preview"><strong>{{ ocrPreview.filename }}</strong><small>{{ ocrPreview.metadata?.page_count || 0 }} 页 · 请抽查低置信度页面</small><p v-for="section in ocrPreview.sections" :key="`${section.page}-${section.title}`">第 {{ section.page }} 页 · {{ section.confidence }}% · {{ section.text_preview || '没有识别到文本。' }}</p></article>
    <p class="material-limit">单文件最多 32MB；一次最多 20 个文件、总计 128MB。PDF 可使用现有 OCR 能力。</p>
    <div class="material-actions"><span v-if="message" role="status">{{ message }}</span><button class="button accent" :disabled="submitting || (tab === 'text' ? !text.trim() : !files.length)" @click="submit">{{ submitting ? (tab === 'files' ? '上传并解析中…' : '提交中…') : '确认导入' }}</button></div><p v-if="warning" class="material-warning" role="status">{{ warning }}</p>
  </section>
</template>

<style scoped>
.material-import { display: grid; gap: 14px; padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }
.material-head { display: flex; justify-content: space-between; gap: 16px; }.material-head h2 { margin: 5px 0 7px; font-family: Georgia, serif; font-size: 25px; font-weight: 400; }.material-hint, .material-limit, .material-options small, .ocr-options small { color: var(--muted); font-size: 11px; line-height: 1.6; }.material-hint { max-width: 620px; margin: 0; }.scope-badge { flex: 0 0 auto; align-self: start; padding: 5px 8px; border: 1px solid rgba(125,164,119,.35); border-radius: 99px; color: #8fae89; font-size: 10px; }
.material-tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--line); }.material-tabs button { padding: 8px 11px; border: 0; border-bottom: 2px solid transparent; color: var(--muted); background: transparent; cursor: pointer; font-size: 11px; }.material-tabs button.active { border-bottom-color: var(--accent); color: var(--accent); }.material-tabs button:disabled { cursor: not-allowed; opacity: .5; }.material-field, .material-options label { display: grid; gap: 6px; color: var(--muted); font-size: 11px; }.material-field input, .material-options select, .material-text { width: 100%; padding: 10px; border: 1px solid var(--line); border-radius: 8px; outline: 0; color: inherit; background: transparent; font: inherit; font-size: 12px; }.material-text { resize: vertical; line-height: 1.6; }.file-picker { display: grid; gap: 7px; }.file-picker input { position: absolute; width: 1px; height: 1px; opacity: 0; }.file-picker-label { display: grid; gap: 6px; padding: 25px 16px; border: 1px dashed var(--line); border-radius: 10px; color: var(--muted); cursor: pointer; text-align: center; }.file-picker-label strong { color: inherit; font-size: 13px; font-weight: 500; }.file-picker-label small { font-size: 10px; }.file-names { margin: 0; overflow: hidden; color: var(--muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.material-options, .ocr-options { display: flex; align-items: end; gap: 12px; flex-wrap: wrap; }.material-options select { width: 170px; }.ocr-options { align-items: center; }.ocr-options label { color: var(--muted); font-size: 11px; }.ocr-options input { accent-color: var(--accent); }.link-button { padding: 0; border: 0; color: var(--accent); background: transparent; cursor: pointer; font-size: 10px; }.link-button:disabled { cursor: not-allowed; opacity: .5; }.ocr-preview { display: grid; gap: 6px; padding: 12px; border: 1px solid var(--line); border-radius: 9px; }.ocr-preview strong { font-size: 12px; }.ocr-preview small, .ocr-preview p { margin: 0; color: var(--muted); font-size: 10px; line-height: 1.6; }.material-actions { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: #8fae89; font-size: 11px; }.material-warning { margin: 0; color: #d18d82; font-size: 11px; line-height: 1.6; }
@media (max-width: 600px) { .material-head, .material-actions { align-items: flex-start; flex-direction: column; }.material-options, .ocr-options { align-items: flex-start; flex-direction: column; }.material-options select { width: 100%; } }
</style>
