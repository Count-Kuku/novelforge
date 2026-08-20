<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useWorkspaceStore } from '../../stores/workspace'
import { api, ApiClientError } from '../../api/client'

const workspace = useWorkspaceStore()
const content = ref('')
const loading = ref(true)
const saving = ref(false)
const saved = ref(false)
const error = ref('')
const contextPreview = ref<Record<string, any> | null>(null)
const contextLoading = ref(false)
const discussionIdea = ref('')
const discussionStep = ref<Record<string, any> | null>(null)
const discussionText = ref('')
const discussing = ref(false)
const approving = ref(false)
const discussionInput = ref<HTMLInputElement | null>(null)

watch(content, () => {
  if (!loading.value) saved.value = false
})

onMounted(async () => {
  if (!workspace.activeProjectId || !workspace.activeStory) { loading.value = false; return }
  try {
    content.value = (await api.outline(workspace.activeProjectId, workspace.activeStory.story_id)).content
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '无法读取大纲'
  } finally {
    loading.value = false
  }
})

async function save() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    await api.updateOutline(workspace.activeProjectId, workspace.activeStory.story_id, content.value)
    saved.value = true
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function previewContext() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  contextLoading.value = true
  try { contextPreview.value = await api.contextPreview(workspace.activeProjectId, workspace.activeStory.story_id, content.value.slice(0, 1200)) as Record<string, any> } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '上下文检查失败' } finally { contextLoading.value = false }
}

async function discussOutline() {
  if (!workspace.activeProjectId || !workspace.activeStory || !discussionIdea.value.trim() || discussing.value) return
  discussing.value = true
  discussionText.value = ''
  error.value = ''
  try {
    await api.streamDiscussion(workspace.activeProjectId, workspace.activeStory.story_id, 'outline', discussionIdea.value.trim(), (event, data) => {
      if (event === 'delta') discussionText.value += String(data?.text || '')
      if (event === 'done') discussionStep.value = data?.result || null
      if (event === 'error') throw new ApiClientError(String(data?.message || '讨论失败'), 500, String(data?.code || 'discussion_failed'))
    })
  } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '讨论失败' } finally { discussing.value = false }
}

async function approveOutlineDiscussion() {
  if (!workspace.activeProjectId || !workspace.activeStory || !discussionStep.value || approving.value) return
  approving.value = true
  try { await api.approveDiscussion(workspace.activeProjectId, workspace.activeStory.story_id, 'outline', discussionStep.value); discussionText.value = '已采用讨论结论并保存到大纲讨论记录。' } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '应用结论失败' } finally { approving.value = false }
}

async function startSuggestedDiscussion() {
  discussionIdea.value = '检查人物设定与世界规则是否足以支撑当前主线'
  await nextTick()
  discussionInput.value?.focus()
}
</script>

<template><section class="outline-page"><p class="eyebrow">02 / 结构与大纲</p><div class="title-row"><div><h2>管理全书主线、<em>转折与结局</em></h2><p>正式大纲单独保存；讨论结果只有在采用后才会进入后续规划。</p></div><span class="pill">正式规划资产</span></div><div v-if="loading" class="outline-state">正在读取大纲…</div><div v-else class="outline-editor"><div class="editor-heading"><div><p class="eyebrow">正式大纲</p><h3>全书大纲</h3></div><span v-if="saved" class="saved-state">已保存</span></div><textarea v-model="content" rows="14" placeholder="记录故事主线、关键转折和结局。上下文检查不会修改正式大纲。"></textarea><div class="editor-footer"><span v-if="error" class="error">{{ error }}</span><span v-else class="muted">内容将保存到当前故事。</span><div class="editor-actions"><button class="button secondary" :disabled="contextLoading" @click="previewContext">{{ contextLoading ? '检查中…' : '检查上下文' }}</button><button class="button accent" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存大纲' }}</button></div></div></div><div class="discussion-panel"><div><p class="eyebrow">大纲讨论</p><h3>讨论一个具体的结构问题</h3></div><div class="discussion-row"><input ref="discussionInput" v-model="discussionIdea" placeholder="例如：第二幕转折是否足够明确？" @keydown.enter="discussOutline" /><button class="button secondary" :disabled="discussing || !discussionIdea.trim()" @click="discussOutline">{{ discussing ? '讨论中…' : '开始讨论' }}</button></div><div v-if="discussionText" class="discussion-result"><p>{{ discussionText }}<span v-if="discussing" class="discussion-cursor">▌</span></p><button v-if="discussionStep" class="button accent" :disabled="approving" @click="approveOutlineDiscussion">{{ approving ? '应用中…' : '采用这份结论' }}</button></div></div><div v-if="contextPreview" class="context-panel"><div><p class="eyebrow">上下文检查</p><h3>本次生成上下文</h3></div><div class="context-metrics"><span><strong>{{ contextPreview.total_estimated_tokens || 0 }}</strong>预计 tokens</span><span><strong>{{ contextPreview.included_block_count || 0 }}</strong>纳入块</span><span><strong>{{ contextPreview.omitted_block_count || 0 }}</strong>省略块</span></div><p class="muted">{{ (contextPreview.warnings || []).join('；') || '当前预算内未发现警告。' }}</p></div><div class="outline-board"><div class="board-column"><span class="column-index">01</span><h3>故事命题</h3><p>检查核心冲突、主角目标和故事承诺。</p><div class="ghost-line"></div><div class="ghost-line short"></div></div><div class="board-column highlighted"><span class="column-index">02</span><h3>世界与人物</h3><p>检查人物动机、关系和世界规则是否支撑主线。</p><button class="button secondary" @click="startSuggestedDiscussion">带入讨论 <span>→</span></button></div><div class="board-column"><span class="column-index">03</span><h3>章节节奏</h3><p>检查关键转折的章节位置和前后铺垫。</p><div class="ghost-line"></div><div class="ghost-line short"></div></div></div></section>
</template>
<style scoped>
.outline-page { max-width: 1180px; margin: 0 auto; }.title-row { display: flex; align-items: end; justify-content: space-between; gap: 25px; margin: 10px 0 45px; }.title-row h2 { margin: 0; font-family: Georgia, serif; font-size: clamp(35px, 4.6vw, 59px); font-weight: 400; letter-spacing: -.055em; }.title-row h2 em { color: var(--accent); font-style: normal; }.title-row p { margin: 18px 0 0; color: var(--muted); font-size: 14px; }.outline-board { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }.board-column { min-height: 310px; padding: 28px; border: 1px solid var(--line); border-radius: 20px; background: rgba(255,253,249,.65); }.board-column.highlighted { color: #f8f2e9; border-color: #3c3833; background: #363330; box-shadow: 0 18px 50px rgba(57,45,35,.13); }.column-index { color: var(--accent); font-family: Georgia, serif; font-size: 21px; }.board-column h3 { margin: 32px 0 15px; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.board-column p { color: var(--muted); font-size: 13px; line-height: 1.8; }.highlighted p { color: #ada69b; }.board-column .button { margin-top: 32px; }.ghost-line { width: 82%; height: 8px; margin-top: 45px; border-radius: 99px; background: #e9e1d6; }.ghost-line.short { width: 52%; margin-top: 10px; }.highlighted .ghost-line { background: #4e4943; }
.outline-page { max-width: 1180px; margin: 0 auto; }.title-row { display: flex; align-items: end; justify-content: space-between; gap: 25px; margin: 10px 0 45px; }.title-row h2 { margin: 0; font-family: Georgia, serif; font-size: clamp(35px, 4.6vw, 59px); font-weight: 400; letter-spacing: -.055em; }.title-row h2 em { color: var(--accent); font-style: normal; }.title-row p { margin: 18px 0 0; color: var(--muted); font-size: 14px; }.outline-state { min-height: 130px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }.outline-editor { margin-bottom: 20px; padding: 22px; border: 1px solid #e8d3c3; border-radius: 18px; background: #fffaf4; }.editor-heading, .editor-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; }.editor-heading h3 { margin: 4px 0 0; font-family: Georgia, serif; font-size: 22px; font-weight: 400; }.saved-state { color: #778d72; font-size: 12px; }.outline-editor textarea { width: 100%; margin-top: 18px; resize: vertical; border: 1px solid var(--line); border-radius: 11px; padding: 14px; outline: none; color: #51483f; background: #fffdf9; font-family: Georgia, serif; font-size: 15px; line-height: 1.8; }.outline-editor textarea:focus { border-color: #ca8568; box-shadow: 0 0 0 3px rgba(202,133,104,.12); }.editor-footer { margin-top: 12px; }.error { color: #b55f46; font-size: 12px; }.outline-board { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }.board-column { min-height: 310px; padding: 28px; border: 1px solid var(--line); border-radius: 20px; background: rgba(255,253,249,.65); }.board-column.highlighted { color: #f8f2e9; border-color: #3c3833; background: #363330; box-shadow: 0 18px 50px rgba(57,45,35,.13); }.column-index { color: var(--accent); font-family: Georgia, serif; font-size: 21px; }.board-column h3 { margin: 32px 0 15px; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.board-column p { color: var(--muted); font-size: 13px; line-height: 1.8; }.highlighted p { color: #ada69b; }.board-column .button { margin-top: 32px; }.ghost-line { width: 82%; height: 8px; margin-top: 45px; border-radius: 99px; background: #e9e1d6; }.ghost-line.short { width: 52%; margin-top: 10px; }.highlighted .ghost-line { background: #4e4943; }
@media (max-width: 760px) { .title-row { align-items: flex-start; flex-direction: column; }.outline-board { grid-template-columns: 1fr; }.board-column { min-height: 220px; } }
</style>

<style scoped>
.discussion-panel { display: grid; gap: 14px; margin: 0 0 20px; padding: 22px; border: 1px solid #dfcfbe; border-radius: 16px; background: #fbf5ed; }.discussion-panel h3 { margin: 4px 0 0; font-family: Georgia, serif; font-size: 22px; font-weight: 400; }.discussion-row { display: flex; gap: 8px; }.discussion-row input { flex: 1; min-width: 0; padding: 10px 12px; border: 1px solid #e6d5c6; border-radius: 8px; outline: 0; color: #544940; background: #fffdf9; }.discussion-result { padding: 14px; border-radius: 10px; color: #66594e; background: #f2e7da; font-size: 13px; line-height: 1.7; }.discussion-result p { margin: 0 0 10px; }.discussion-cursor { color: #b76849; animation: blink-discussion 1s steps(2,start) infinite; } @keyframes blink-discussion { 50% { opacity: 0; } }
</style>

<style scoped>
.editor-actions { display: flex; gap: 8px; }.context-panel { display: grid; gap: 14px; margin: 0 0 20px; padding: 22px; border: 1px solid #dfcfbe; border-radius: 16px; background: #f5eee5; }.context-panel h3 { margin: 4px 0 0; font-family: Georgia, serif; font-size: 22px; font-weight: 400; }.context-metrics { display: flex; flex-wrap: wrap; gap: 26px; color: #817367; font-size: 11px; }.context-metrics strong { margin-right: 5px; color: #a65d41; font-family: Georgia, serif; font-size: 22px; font-weight: 400; }
</style>
