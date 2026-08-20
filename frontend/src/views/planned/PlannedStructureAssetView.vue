<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, ApiClientError } from '../../api/client'
import { useWorkspaceStore } from '../../stores/workspace'
import { dialog } from '../../ui/dialog'

const route = useRoute()
const workspace = useWorkspaceStore()
const assetType = computed(() => String(route.meta.assetType || 'volume') as 'volume' | 'arc')
const assetNo = computed(() => Number(route.params.assetNo || 1))
const outline = ref('')
const metadata = ref<Record<string, any>>({})
const discussion = ref<Record<string, any>>({})
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)
const discussionIdea = ref('')
const discussionText = ref('')
const discussionStep = ref<Record<string, any> | null>(null)
const discussing = ref(false)
const approving = ref(false)
const deleting = ref(false)
const chapterPlanJson = ref('{}')
const chapterPlanReport = ref('')
const chapterPlanSaving = ref(false)
const planValidation = ref<Record<string, any> | null>(null)

watch(outline, () => {
  if (!loading.value) saved.value = false
})

async function loadAsset() {
  if (!workspace.activeProjectId || !workspace.activeStory) { loading.value = false; return }
  loading.value = true
  try {
    const data = assetType.value === 'volume'
      ? await api.volume(workspace.activeProjectId, workspace.activeStory.story_id, assetNo.value)
      : await api.arc(workspace.activeProjectId, workspace.activeStory.story_id, assetNo.value)
    metadata.value = (data.metadata || {}) as Record<string, any>
    outline.value = String(data.outline || '')
    discussion.value = (data.discussion || {}) as Record<string, any>
    if (assetType.value === 'arc') {
      const plan = await api.arcChapterPlan(workspace.activeProjectId, workspace.activeStory.story_id, assetNo.value)
      chapterPlanJson.value = JSON.stringify(plan.plan || plan, null, 2)
      chapterPlanReport.value = String(plan.report_markdown || '')
    }
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '无法读取结构资产' } finally { loading.value = false }
}

async function saveChapterPlan() {
  if (assetType.value !== 'arc' || !workspace.activeProjectId || !workspace.activeStory || chapterPlanSaving.value) return
  chapterPlanSaving.value = true
  try { const payload = JSON.parse(chapterPlanJson.value); planValidation.value = await api.validateArcChapterPlan(workspace.activeProjectId, workspace.activeStory.story_id, assetNo.value, payload); if (planValidation.value.valid === false) { error.value = '章节计划存在结构冲突，已保留在编辑器中。'; return } await api.updateArcChapterPlan(workspace.activeProjectId, workspace.activeStory.story_id, assetNo.value, payload, chapterPlanReport.value); discussionText.value = '章节计划已保存，结构校验通过。' }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '章节计划保存失败' }
  finally { chapterPlanSaving.value = false }
}

async function save() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  saving.value = true
  saved.value = false
  try {
    if (assetType.value === 'volume') await api.updateVolume(workspace.activeProjectId, workspace.activeStory.story_id, assetNo.value, outline.value)
    else await api.updateArc(workspace.activeProjectId, workspace.activeStory.story_id, assetNo.value, outline.value)
    saved.value = true
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '保存失败' } finally { saving.value = false }
}

async function discuss() {
  if (!workspace.activeProjectId || !workspace.activeStory || !discussionIdea.value.trim() || discussing.value) return
  discussing.value = true
  discussionText.value = ''
  try { await api.streamDiscussion(workspace.activeProjectId, workspace.activeStory.story_id, assetType.value, discussionIdea.value.trim(), (event, data) => { if (event === 'delta') discussionText.value += String(data?.text || ''); if (event === 'done') discussionStep.value = data?.result || null }, assetNo.value) } catch (reason) { discussionText.value = reason instanceof ApiClientError ? reason.message : '讨论失败' } finally { discussing.value = false }
}

async function approveDiscussion() {
  if (!workspace.activeProjectId || !workspace.activeStory || !discussionStep.value || approving.value) return
  approving.value = true
  try { await api.approveDiscussion(workspace.activeProjectId, workspace.activeStory.story_id, assetType.value, discussionStep.value, assetNo.value); discussionText.value = '已采用讨论结论并更新当前结构。' } catch (reason) { discussionText.value = reason instanceof ApiClientError ? reason.message : '应用结论失败' } finally { approving.value = false }
}

async function deleteAsset() {
  if (!workspace.activeProjectId || !workspace.activeStory || deleting.value) return
  const label = assetType.value === 'volume' ? `第 ${assetNo.value} 卷` : `剧情段 ${assetNo.value}`
  if (!await dialog.confirm({ title: `删除${label}？`, message: '相关结构资产会一并移除，此操作无法在界面中撤销。', confirmLabel: '删除结构', tone: 'danger' })) return
  deleting.value = true
  try {
    if (assetType.value === 'volume') await api.deleteVolume(workspace.activeProjectId, workspace.activeStory.story_id, assetNo.value)
    else await api.deleteArc(workspace.activeProjectId, workspace.activeStory.story_id, assetNo.value)
    globalThis.history.back()
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '删除失败' } finally { deleting.value = false }
}

onMounted(loadAsset)
</script>

<template>
  <section class="asset-page">
    <p class="eyebrow">{{ assetType === 'volume' ? '分卷规划' : '剧情段规划' }}</p>
    <div class="asset-heading"><div><h2>{{ assetType === 'volume' ? `第 ${assetNo} 卷` : `剧情段 ${assetNo}` }}</h2><p>{{ metadata.title || metadata.name || '未命名结构' }} · 编辑大纲、章节分配和讨论记录。</p></div><div class="asset-heading-actions"><span class="pill">{{ saved ? '已保存' : '未保存修改' }}</span><button class="danger-action" :disabled="deleting" @click="deleteAsset">{{ deleting ? '删除中…' : '删除' }}</button></div></div>
    <div v-if="loading" class="asset-state">正在读取结构…</div>
    <template v-else>
      <article v-if="assetType === 'arc'" class="chapter-plan-panel"><p class="eyebrow">章节计划</p><h3>章节分配与冲突检查</h3><p class="plan-hint">保存前会检查重复章节、剧情段重叠、预计章节数和现有归属。存在冲突时不会写入。</p><textarea v-model="chapterPlanJson" rows="8" aria-label="章节计划 JSON"></textarea><textarea v-model="chapterPlanReport" rows="4" placeholder="冲突处理或人工裁决说明"></textarea><button class="button secondary" :disabled="chapterPlanSaving" @click="saveChapterPlan">{{ chapterPlanSaving ? '校验中…' : '校验并保存' }}</button><div v-if="planValidation" class="validation-box" :class="{ invalid: !planValidation.valid }"><strong>{{ planValidation.valid ? '校验通过' : '发现结构冲突' }}</strong><span v-for="item in (planValidation.conflicts || planValidation.warnings || [])" :key="`${item.code}-${item.chapter_no || item.index}`">{{ item.message }}</span></div></article>
      <div class="asset-grid"><article class="asset-editor"><div class="editor-head"><div><p class="eyebrow">正式大纲</p><h3>{{ assetType === 'volume' ? '分卷大纲' : '剧情段大纲' }}</h3></div><button class="button accent" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存大纲' }}</button></div><textarea v-model="outline" rows="18" placeholder="记录阶段目标、冲突推进和章节边界"></textarea><p v-if="error" class="asset-error">{{ error }}</p><article class="asset-discussion"><p class="eyebrow">结构讨论</p><h3>讨论当前结构中的具体问题</h3><div class="discussion-row"><input v-model="discussionIdea" placeholder="例如：这一卷的中点转折是否太晚？" @keydown.enter="discuss" /><button class="button secondary" :disabled="discussing || !discussionIdea.trim()" @click="discuss">{{ discussing ? '讨论中…' : '开始讨论' }}</button></div><div v-if="discussionText" class="discussion-result"><p>{{ discussionText }}<span v-if="discussing">▌</span></p><button v-if="discussionStep" class="button accent" :disabled="approving" @click="approveDiscussion">{{ approving ? '应用中…' : '采用并应用' }}</button></div></article></article><aside class="asset-inspector"><p class="eyebrow">结构信息</p><h3>当前状态</h3><dl><div v-for="(value, key) in metadata" :key="key"><dt>{{ key }}</dt><dd>{{ typeof value === 'object' ? JSON.stringify(value) : value }}</dd></div></dl><div class="approval-card"><strong>{{ discussion.approval_ready ? '已有可采用的讨论结论' : '暂无可采用的讨论结论' }}</strong><small>采用后的结论会加入后续生成上下文。</small></div></aside></div>
    </template>
  </section>
</template>

<style scoped>
.asset-page { max-width: 1160px; margin: 0 auto; }.asset-heading { display: flex; align-items: end; justify-content: space-between; gap: 22px; margin: 12px 0 42px; }.asset-heading h2 { margin: 0; font-family: Georgia, serif; font-size: clamp(36px, 5vw, 62px); font-weight: 400; letter-spacing: -.055em; }.asset-heading h2 em { color: var(--accent); font-style: normal; }.asset-heading p { margin: 15px 0 0; color: var(--muted); font-size: 13px; }.asset-state { min-height: 220px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }.asset-grid { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(260px, .75fr); gap: 18px; }.asset-editor, .asset-inspector { padding: 24px; border: 1px solid var(--line); border-radius: 18px; background: rgba(255,253,249,.7); }.editor-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }.editor-head h3, .asset-inspector h3 { margin: 4px 0 0; font-family: Georgia, serif; font-size: 23px; font-weight: 400; }.asset-editor textarea { width: 100%; margin-top: 18px; padding: 14px; resize: vertical; border: 1px solid var(--line); border-radius: 10px; outline: 0; color: #51483f; background: #fffdf9; font-family: Georgia, serif; font-size: 15px; line-height: 1.8; }.asset-inspector { background: #e9e1d6; }.asset-inspector dl { display: grid; gap: 10px; margin: 22px 0; }.asset-inspector dl div { display: grid; gap: 3px; padding-bottom: 9px; border-bottom: 1px solid rgba(117,108,98,.16); }.asset-inspector dt { color: #9b8d80; font-size: 10px; }.asset-inspector dd { margin: 0; overflow-wrap: anywhere; color: #6f6256; font-size: 12px; }.approval-card { display: grid; gap: 7px; margin-top: 24px; padding: 13px; border-radius: 10px; background: rgba(255,255,255,.35); }.approval-card strong { color: #725e51; font-size: 12px; }.approval-card small { color: #8c7c6f; font-size: 11px; line-height: 1.6; }.asset-error { color: #b55f46; font-size: 12px; }
.chapter-plan-panel { display: grid; gap: 10px; margin-bottom: 16px; padding: 18px; border: 1px solid var(--line); border-radius: 14px; background: rgba(255,253,249,.7); }.chapter-plan-panel h3 { margin: 0; font-family: Georgia, serif; font-size: 22px; font-weight: 400; }.plan-hint { margin: 0; color: var(--muted); font-size: 11px; line-height: 1.6; }.chapter-plan-panel textarea { width: 100%; padding: 10px; resize: vertical; border: 1px solid var(--line); border-radius: 8px; color: #51483f; background: #fffdf9; font: 11px/1.6 ui-monospace, monospace; }
.validation-box { display: grid; gap: 5px; padding: 10px; border-radius: 9px; color: #4c7353; background: #edf5e9; font-size: 11px; line-height: 1.5; }.validation-box.invalid { color: #9b5144; background: #fff0eb; }.danger-action { display: block; margin: 0 0 12px auto; padding: 6px 9px; border: 1px solid rgba(181,95,70,.34); border-radius: 7px; color: #b55f46; background: transparent; cursor: pointer; font-size: 10px; }.danger-action:hover { border-color: #b55f46; background: rgba(181,95,70,.06); }
.asset-discussion { margin-top: 20px; padding-top: 18px; border-top: 1px solid var(--line); }.asset-discussion h3 { margin: 5px 0 14px; font-family: Georgia, serif; font-size: 21px; font-weight: 400; }.discussion-row { display: flex; gap: 8px; }.discussion-row input { flex: 1; min-width: 0; padding: 10px; border: 1px solid var(--line); border-radius: 8px; outline: 0; background: #fffdf9; }.discussion-result { margin-top: 12px; padding: 12px; border-radius: 10px; background: #f7efe5; color: #6f6256; font-size: 12px; line-height: 1.7; }.discussion-result p { margin: 0 0 8px; }
.asset-heading-actions { display: flex; align-items: center; gap: 9px; }.asset-heading-actions .danger-action { margin: 0; padding: 7px 10px; font-size: 11px; }
@media (max-width: 760px) { .asset-heading { align-items: flex-start; flex-direction: column; }.asset-grid { grid-template-columns: 1fr; } }
</style>
