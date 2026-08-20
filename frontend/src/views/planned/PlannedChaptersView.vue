<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useWorkspaceStore } from '../../stores/workspace'
import { api } from '../../api/client'

const workspace = useWorkspaceStore()
const chapters = ref<any[]>([])
const loading = ref(true)
const selectedNo = ref<number | null>(null)
const chapterContent = ref('')
const chapterOutline = ref('')
const chapterReview = ref('')
const editorKind = ref<'content' | 'outline'>('content')
const saving = ref(false)
const editorError = ref('')
const editorMessage = ref('')
const discussionIdea = ref('')
const discussionText = ref('')
const discussionStep = ref<Record<string, any> | null>(null)
const discussing = ref(false)
const approving = ref(false)
const versions = ref<any[]>([])
const selectedVersion = ref<any | null>(null)

watch([chapterContent, chapterOutline, editorKind], () => {
  if (!saving.value) editorMessage.value = ''
})

onMounted(async () => {
  if (workspace.activeProjectId && workspace.activeStory) {
    try { chapters.value = (await api.workspace(workspace.activeProjectId, workspace.activeStory.story_id)).chapters as any[] } catch (reason) { chapters.value = []; console.warn('Chapter workspace unavailable', reason) }
  }
  loading.value = false
})

async function openChapter(chapterNo: number) {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  selectedNo.value = chapterNo
  editorError.value = ''
  editorMessage.value = ''
  try {
    const data = await api.chapter(workspace.activeProjectId, workspace.activeStory.story_id, chapterNo)
    chapterContent.value = data.content || ''
    chapterOutline.value = data.outline || ''
    chapterReview.value = data.review || ''
    versions.value = (await api.chapterVersions(workspace.activeProjectId, workspace.activeStory.story_id, chapterNo)).versions || []
  } catch (reason) { editorError.value = reason instanceof Error ? reason.message : '无法读取章节' }
}

async function discussChapter() {
  if (!selectedNo.value || !workspace.activeProjectId || !workspace.activeStory || !discussionIdea.value.trim() || discussing.value) return
  discussing.value = true
  discussionText.value = ''
  try { await api.streamDiscussion(workspace.activeProjectId, workspace.activeStory.story_id, 'chapter', discussionIdea.value.trim(), (event, data) => { if (event === 'delta') discussionText.value += String(data?.text || ''); if (event === 'done') discussionStep.value = data?.result || null }, selectedNo.value) } catch (reason) { discussionText.value = reason instanceof Error ? reason.message : '章节讨论失败' } finally { discussing.value = false }
}

async function approveChapterDiscussion() {
  if (!selectedNo.value || !workspace.activeProjectId || !workspace.activeStory || !discussionStep.value || approving.value) return
  approving.value = true
  try { await api.approveDiscussion(workspace.activeProjectId, workspace.activeStory.story_id, 'chapter', discussionStep.value, selectedNo.value); discussionText.value = '已采用章节讨论结论。' } catch (reason) { discussionText.value = reason instanceof Error ? reason.message : '应用结论失败' } finally { approving.value = false }
}

function showVersion(version: any) {
  selectedVersion.value = selectedVersion.value?.version_id === version.version_id ? null : version
}

async function saveChapter() {
  if (!selectedNo.value || !workspace.activeProjectId || !workspace.activeStory) return
  saving.value = true
  editorError.value = ''
  editorMessage.value = ''
  try {
    const content = editorKind.value === 'content' ? chapterContent.value : chapterOutline.value
    await api.updateChapter(workspace.activeProjectId, workspace.activeStory.story_id, selectedNo.value, content, editorKind.value)
    editorMessage.value = editorKind.value === 'content' ? '正文已保存' : '章节细纲已保存'
  } catch (reason) { editorError.value = reason instanceof Error ? reason.message : '保存失败' } finally { saving.value = false }
}
</script>
<template><section class="chapters-page"><p class="eyebrow">03 / 章节推进</p><h2>编辑章节细纲和<em>正文</em></h2><p class="intro">选择章节后，可编辑正文或细纲、讨论具体问题，并查看历史版本和审阅结果。</p><div v-if="loading" class="chapter-loading">正在读取章节结构…</div><div v-else class="chapter-layout"><div class="chapter-list"><button v-for="chapter in (chapters.length ? chapters : [{ chapter_no: 1, title: '第 1 章', has_content: false }])" :key="chapter.chapter_no" class="chapter-row" :class="{ selected: selectedNo === chapter.chapter_no }" @click="openChapter(chapter.chapter_no)"><span class="chapter-no">{{ String(chapter.chapter_no).padStart(2, '0') }}</span><span><strong>{{ chapter.title || `第${chapter.chapter_no}章` }}</strong><small>{{ workspace.activeStory?.name || '当前故事' }} · {{ chapter.has_content ? '已有正文' : '尚无正文' }}</small></span><span class="status" :class="{ 'muted-status': !chapter.has_content }">{{ chapter.has_content ? '已写作' : '未开始' }}</span><b>→</b></button></div><aside class="chapter-structure"><p class="eyebrow">结构归属</p><h3>卷与剧情段</h3><p>显示各章当前所属的分卷和剧情段，便于检查未归类章节。</p><div v-for="chapter in chapters.slice(0, 8)" :key="`context-${chapter.chapter_no}`" class="context-row"><span>第 {{ chapter.chapter_no }} 章</span><small>{{ chapter.volume_no ? `卷 ${chapter.volume_no}` : '未分卷' }} · {{ chapter.arc_no ? `剧情段 ${chapter.arc_no}` : '未分段' }}</small></div></aside></div><div v-if="selectedNo" class="chapter-editor"><div class="editor-top"><div><p class="eyebrow">第 {{ String(selectedNo).padStart(2, '0') }} 章</p><h3>章节编辑</h3></div><select v-model="editorKind" aria-label="编辑内容类型"><option value="content">正文</option><option value="outline">章节细纲</option></select></div><textarea v-if="editorKind === 'content'" v-model="chapterContent" rows="15" placeholder="输入章节正文"></textarea><textarea v-else v-model="chapterOutline" rows="10" placeholder="记录本章目标、冲突和关键事件"></textarea><div class="editor-footer"><span v-if="editorError" class="editor-error">{{ editorError }}</span><span v-else-if="editorMessage" class="saved-state">{{ editorMessage }}</span><span v-else class="muted">保存到当前故事。</span><button class="button accent" :disabled="saving" @click="saveChapter">{{ saving ? '保存中…' : editorKind === 'content' ? '保存正文' : '保存细纲' }}</button></div><article class="chapter-discussion"><p class="eyebrow">章节讨论</p><div class="discussion-row"><input v-model="discussionIdea" placeholder="输入本章要讨论的问题" @keydown.enter="discussChapter" /><button class="button secondary" :disabled="discussing || !discussionIdea.trim()" @click="discussChapter">{{ discussing ? '讨论中…' : '开始讨论' }}</button></div><div v-if="discussionText" class="discussion-result"><p>{{ discussionText }}<span v-if="discussing">▌</span></p><button v-if="discussionStep" class="button accent" :disabled="approving" @click="approveChapterDiscussion">{{ approving ? '应用中…' : '采用讨论结论' }}</button></div></article><article v-if="versions.length" class="version-panel"><p class="eyebrow">历史版本</p><button v-for="version in versions" :key="version.version_id" class="version-row" @click="showVersion(version)"><span>{{ version.label }}</span><small>{{ version.updated_at || '当前' }}</small></button><pre v-if="selectedVersion">{{ selectedVersion.content }}</pre></article><article v-if="chapterReview" class="review-panel"><p class="eyebrow">章节审阅</p><pre>{{ chapterReview }}</pre></article></div></section></template>
<style scoped>
.chapters-page { max-width: 900px; margin: 0 auto; }.chapters-page h2 { max-width: 700px; margin: 12px 0 18px; font-family: Georgia, serif; font-size: clamp(37px, 5vw, 63px); font-weight: 400; letter-spacing: -.055em; line-height: 1.08; }.chapters-page h2 em { color: var(--accent); font-style: normal; }.intro { max-width: 500px; color: var(--muted); font-size: 14px; line-height: 1.8; }.chapter-loading { min-height: 180px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }.chapter-list { margin-top: 50px; border-top: 1px solid var(--line); }.chapter-row { display: grid; grid-template-columns: 55px 1fr auto 24px; align-items: center; gap: 14px; padding: 22px 6px; border-bottom: 1px solid var(--line); }.chapter-row.active { padding: 25px 18px; border: 1px solid #e7d2c3; border-top: 0; background: #fff9f2; }.chapter-no { color: var(--accent); font-family: Georgia, serif; font-size: 19px; }.chapter-row strong { display: block; font-family: Georgia, serif; font-size: 18px; font-weight: 400; }.chapter-row small { display: block; margin-top: 6px; color: var(--muted); font-size: 12px; }.status { color: #ae6043; font-size: 12px; }.muted-status { color: #aaa097; }.chapter-row b { color: var(--accent); font-weight: 400; }
</style>

<style scoped>
.chapter-row { width: 100%; border: 0; color: inherit; background: transparent; cursor: pointer; text-align: left; }
.chapter-layout { display: grid; grid-template-columns: minmax(0, 1fr) 250px; gap: 16px; margin-top: 50px; }.chapter-layout .chapter-list { margin-top: 0; }.chapter-structure { padding: 18px; border: 1px solid var(--line); border-radius: 14px; color: #6f6256; background: #f5ece1; }.chapter-structure h3 { margin: 5px 0 8px; font-family: Georgia, serif; font-size: 21px; font-weight: 400; }.chapter-structure p:not(.eyebrow) { color: #8c7c6f; font-size: 11px; line-height: 1.6; }.context-row { display: grid; gap: 3px; padding: 8px 0; border-top: 1px solid rgba(117,108,98,.16); font-size: 11px; }.context-row small { color: #9b8d80; font-size: 10px; }.chapter-discussion { margin-top: 20px; padding-top: 18px; border-top: 1px solid var(--line); }.discussion-row { display: flex; gap: 8px; }.discussion-row input { flex: 1; min-width: 0; padding: 10px; border: 1px solid var(--line); border-radius: 8px; background: #fffdf9; }.discussion-result { margin-top: 10px; padding: 11px; border-radius: 9px; color: #6f6256; background: #f7efe5; font-size: 12px; line-height: 1.7; }.version-panel { margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--line); }.version-row { display: flex; justify-content: space-between; width: 100%; padding: 8px 0; border: 0; border-bottom: 1px solid var(--line); color: #6f6256; background: transparent; cursor: pointer; font-size: 11px; text-align: left; }.version-row small { color: #9b8d80; }.version-panel pre { max-height: 220px; margin-top: 10px; padding: 12px; overflow: auto; color: #6f6256; background: #f7efe5; font: 11px/1.6 ui-monospace, monospace; white-space: pre-wrap; }
.chapter-row.selected { box-shadow: inset 3px 0 #c67958; }
.chapter-editor { margin-top: 20px; padding: 24px; border: 1px solid #e7d2c3; border-radius: 18px; background: #fffaf4; }
.editor-top, .editor-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.editor-top h3 { margin: 4px 0 0; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }
.editor-top select { padding: 8px 10px; border: 1px solid #e8d3c3; border-radius: 8px; color: #5d5148; background: #fffdf9; }
.chapter-editor textarea { width: 100%; margin-top: 18px; padding: 14px; resize: vertical; border: 1px solid #eaded3; border-radius: 10px; outline: 0; color: #51483f; background: #fffdf9; font-family: Georgia, serif; font-size: 15px; line-height: 1.8; }
.editor-footer { margin-top: 12px; }.editor-error { color: #b55f46; font-size: 12px; }.saved-state { color: #67805f; font-size: 12px; }
.review-panel { margin-top: 18px; padding: 16px; border: 1px solid #eaded3; border-radius: 12px; background: #f7efe5; }.review-panel pre { max-height: 240px; margin: 8px 0 0; overflow: auto; color: #6f6256; font: 12px/1.7 ui-monospace, monospace; white-space: pre-wrap; }
</style>
