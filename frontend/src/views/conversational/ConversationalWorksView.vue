<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiClientError } from '../../api/client'
import { useWorkspaceStore } from '../../stores/workspace'
import { dialog } from '../../ui/dialog'
import { notify } from '../../ui/notifications'

const workspace = useWorkspaceStore()
const items = ref<any[]>([])
const total = ref(0)
const nextCursor = ref('')
const loading = ref(false)
const detailLoading = ref(false)
const selected = ref<any | null>(null)
const selectedContent = ref('')
const error = ref('')
const errorHint = ref('')
const removingId = ref('')

function formatTime(value: unknown) {
  const text = String(value || '')
  if (!text) return '时间未知'
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString('zh-CN', { hour12: false })
}

async function load(cursor = '') {
  if (!workspace.activeProjectId || !workspace.activeStory || loading.value) return
  loading.value = true
  error.value = ''
  errorHint.value = ''
  try {
    const data = await api.works(workspace.activeProjectId, workspace.activeStory.story_id, cursor, 40, workspace.activeBranchId || undefined)
    items.value = cursor ? [...items.value, ...data.items] : data.items
    total.value = data.total || items.value.length
    nextCursor.value = data.next_cursor || ''
  } catch (reason) {
    if (reason instanceof ApiClientError && reason.status === 404) {
      error.value = '作品服务尚未就绪'
      errorHint.value = '请重启 NovelForge 后重新尝试，已经保存的内容不会受到影响。'
    } else {
      error.value = '暂时无法读取作品'
      errorHint.value = '请稍后重新尝试。'
    }
  } finally { loading.value = false }
}

async function openWork(item: any) {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  if (selected.value?.id === item.id) { selected.value = null; selectedContent.value = ''; return }
  selected.value = item
  selectedContent.value = ''
  error.value = ''
  errorHint.value = ''
  detailLoading.value = true
  try {
    if (item.kind === 'chapter') {
      const data = await api.chapter(workspace.activeProjectId, workspace.activeStory.story_id, Number(item.chapter_no))
      selectedContent.value = data.content || item.preview || ''
    } else {
      const data = await api.session(workspace.activeProjectId, workspace.activeStory.story_id, String(item.session_id), workspace.activeBranchId || undefined)
      selectedContent.value = data.fragments.find((fragment) => fragment.fragment_id === item.fragment_id)?.content || item.preview || ''
    }
  } catch (reason) {
    error.value = '暂时无法读取完整正文'
    errorHint.value = '当前先显示已保存的摘要，你可以稍后重新打开。'
    selectedContent.value = item.preview || ''
  } finally { detailLoading.value = false }
}

async function removeWork(item: any) {
  if (!workspace.activeProjectId || !workspace.activeStory || removingId.value) return
  const isChapter = item.kind === 'chapter'
  const confirmed = await dialog.confirm({
    title: isChapter ? `删除“${item.title}”的正文？` : '从作品中移除这个片段？',
    message: isChapter
      ? '只删除已保存的章节正文；章节大纲和相关对话仍会保留。此操作无法在作品页撤销。'
      : '片段会从作品列表消失，但来源对话仍会保留，方便继续写作或回看。',
    confirmLabel: isChapter ? '删除正文' : '移出作品',
    tone: 'danger',
  })
  if (!confirmed) return
  removingId.value = item.id
  try {
    let succeeded = false
    if (isChapter) {
      const result = await api.deleteChapterWork(workspace.activeProjectId, workspace.activeStory.story_id, Number(item.chapter_no), workspace.activeBranchId || undefined)
      succeeded = result.deleted
    } else {
      const result = await api.removeFragmentWork(workspace.activeProjectId, workspace.activeStory.story_id, String(item.fragment_id), workspace.activeBranchId || undefined)
      succeeded = result.removed
    }
    if (!succeeded) throw new Error('这项作品已经不存在')
    if (selected.value?.id === item.id) { selected.value = null; selectedContent.value = '' }
    await load()
    notify(isChapter ? '章节正文已删除' : '片段已移出作品', 'success')
  } catch (reason) { notify(reason instanceof Error ? reason.message : '作品处理失败', 'error') }
  finally { removingId.value = '' }
}

onMounted(() => load())
</script>

<template>
  <section class="works-page">
    <p class="eyebrow">作品</p>
    <div class="works-heading"><div><h1>保存下来的<em>正文内容</em></h1><p>这里只展示已采用或已定稿的对话片段，以及正式保存的章节。完整聊天过程仍保留在“对话”的最近会话中。</p></div><span>{{ error && !items.length ? '暂不可用' : `${total} 项作品` }}</span></div>
    <div v-if="loading && !items.length" class="works-state">正在整理作品…</div>
    <div v-else-if="error && !items.length" class="works-state works-state-error" role="alert"><div><span class="state-mark">↻</span><strong>{{ error }}</strong><p>{{ errorHint }}</p><button class="button secondary" @click="load()">重新尝试</button></div></div>
    <div v-else-if="!items.length" class="works-state"><div><strong>还没有保存的作品</strong><p>在对话中采用一个生成片段，或保存章节后，它会出现在这里。</p></div></div>
    <div v-else class="works-list">
      <article v-for="item in items" :key="item.id" class="work-card" :class="{ selected: selected?.id === item.id }">
        <div class="work-row"><button class="work-open" @click="openWork(item)"><span class="work-kind">{{ item.kind === 'chapter' ? '章' : '文' }}</span><span class="work-copy"><small>{{ item.subtitle }}</small><strong>{{ item.title }}</strong><span>{{ item.preview }}</span></span><span class="work-meta">{{ item.word_count || 0 }} 字<br />{{ formatTime(item.updated_at) }}</span></button><button class="work-remove" :disabled="Boolean(removingId)" @click="removeWork(item)">{{ removingId === item.id ? '处理中…' : item.kind === 'chapter' ? '删除正文' : '移出作品' }}</button></div>
        <div v-if="selected?.id === item.id" class="work-detail"><div v-if="detailLoading" class="detail-state">正在读取完整正文…</div><template v-else><pre>{{ selectedContent }}</pre><RouterLink v-if="item.session_id" :to="{ name: 'conversational-session', params: { sessionId: item.session_id } }">打开来源对话 →</RouterLink></template></div>
      </article>
      <button v-if="nextCursor" class="button secondary load-more" :disabled="loading" @click="load(nextCursor)">{{ loading ? '加载中…' : '加载更多' }}</button>
    </div>
    <p v-if="error && items.length" class="works-error" role="status">{{ error }}。{{ errorHint }}</p>
  </section>
</template>

<style scoped>
.works-page { max-width: 1020px; margin: 0 auto; padding: 12px 0 60px; }.works-heading { display: flex; align-items: end; justify-content: space-between; gap: 28px; margin: 10px 0 34px; }.works-heading h1 { margin: 0; font-family: Georgia, serif; font-size: clamp(38px, 5vw, 62px); font-weight: 400; letter-spacing: -.055em; }.works-heading h1 em { color: var(--accent); font-style: normal; }.works-heading p { max-width: 650px; margin: 16px 0 0; color: var(--muted); font-size: 13px; line-height: 1.8; }.works-heading > span { flex: 0 0 auto; color: var(--muted); font-size: 11px; }.works-list { display: grid; gap: 9px; }.work-card { overflow: hidden; border: 1px solid var(--line); border-radius: 15px; background: rgba(255,255,255,.045); }.work-card.selected { border-color: rgba(211,131,97,.42); }.work-row { display: grid; grid-template-columns: minmax(0,1fr) auto; align-items: center; }.work-open { display: grid; grid-template-columns: 38px minmax(0,1fr) auto; align-items: center; gap: 15px; min-width: 0; padding: 17px 10px 17px 18px; border: 0; color: inherit; background: transparent; text-align: left; }.work-open:hover { background: rgba(255,255,255,.045); }.work-remove { margin-right: 16px; padding: 7px 10px; border: 1px solid rgba(209,104,81,.28); border-radius: 8px; color: #e1aa96; background: rgba(158,66,49,.08); font-size: 10px; white-space: nowrap; }.work-remove:hover { background: rgba(158,66,49,.18); }.work-remove:disabled { opacity: .45; cursor: not-allowed; }.work-kind { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px; color: #e2ae8f; background: rgba(218,157,124,.13); font-family: Georgia, serif; }.work-copy { min-width: 0; }.work-copy small, .work-copy strong, .work-copy > span { display: block; }.work-copy small { color: var(--accent); font-size: 10px; }.work-copy strong { margin-top: 4px; font-family: Georgia, serif; font-size: 18px; font-weight: 400; }.work-copy > span { margin-top: 6px; overflow: hidden; color: var(--muted); font-size: 11px; line-height: 1.6; text-overflow: ellipsis; white-space: nowrap; }.work-meta { color: var(--muted); font-size: 10px; line-height: 1.7; text-align: right; }.work-detail { padding: 0 18px 18px 71px; border-top: 1px solid var(--line); }.work-detail pre { max-height: 420px; margin: 16px 0 12px; overflow: auto; color: #d6d0c7; font: 13px/1.85 Georgia, 'Noto Serif SC', serif; white-space: pre-wrap; }.work-detail a { color: var(--accent); font-size: 11px; }.works-state { min-height: 260px; display: grid; place-items: center; color: var(--muted); text-align: center; }.works-state strong { display: block; color: var(--ink); font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.works-state p { margin: 9px 0 0; font-size: 12px; line-height: 1.7; }.works-state-error > div { max-width: 440px; padding: 26px 30px; border: 1px solid rgba(224,161,125,.2); border-radius: 16px; background: rgba(224,161,125,.055); }.state-mark { display: grid; place-items: center; width: 32px; height: 32px; margin: 0 auto 13px; border-radius: 10px; color: var(--accent); background: rgba(224,161,125,.12); font-size: 18px; }.works-state-error .button { margin-top: 18px; padding: 9px 14px; font-size: 11px; }.detail-state { padding: 22px 0; color: var(--muted); font-size: 11px; }.load-more { justify-self: center; }.works-error { margin-top: 18px; color: #e3a48f; font-size: 12px; line-height: 1.7; }
@media (max-width: 700px) { .works-heading { align-items: flex-start; flex-direction: column; }.work-row { grid-template-columns: 1fr; }.work-open { grid-template-columns: 34px minmax(0,1fr); }.work-meta { grid-column: 2; text-align: left; }.work-remove { justify-self: end; margin: 0 16px 14px; }.work-detail { padding-left: 18px; } }
</style>
