<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore } from '../../stores/workspace'
import { api, ApiClientError } from '../../api/client'

const workspace = useWorkspaceStore()
const router = useRouter()
const idea = ref('')
const creating = ref(false)
const error = ref('')

async function begin() {
  if (!workspace.activeProjectId || !workspace.activeStory || !idea.value.trim()) return
  creating.value = true
  error.value = ''
  try {
    const data = await api.createSession(workspace.activeProjectId, workspace.activeStory.story_id, { session_goal: idea.value.trim() })
    await router.push({ name: 'conversational-session', params: { sessionId: data.session.session_id } })
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '会话创建失败'
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <section class="conversation-home"><div class="welcome"><p class="eyebrow">新建会话</p><h1>这次要讨论或<em>写什么？</em></h1><p>输入一个写作目标、待解决的问题，或直接贴入要续写和修改的内容。</p></div><div class="composer-card"><textarea v-model="idea" rows="4" aria-label="会话目标" placeholder="例如：试写主角多年后回到故乡的开场场景" @keydown.meta.enter.prevent="begin" @keydown.ctrl.enter.prevent="begin"></textarea><div class="composer-footer"><span>⌘ / Ctrl + Enter 创建会话</span><button class="button accent" :disabled="creating || !idea.trim()" @click="begin">{{ creating ? '正在创建…' : '创建会话  →' }}</button></div></div><p v-if="error" class="error">{{ error }}</p><div class="promise-row"><div><span>✦</span><strong>直接开始</strong><small>先创建会话，再按需调整设置</small></div><div><span>⌁</span><strong>保存版本</strong><small>写作片段和采用状态可追溯</small></div><div><span>◌</span><strong>保留上下文</strong><small>附件与确认知识可继续使用</small></div></div></section>
</template>

<style scoped>
.conversation-home { max-width: 780px; margin: clamp(40px, 10vh, 105px) auto 0; padding: 0 26px 70px; }.welcome h1 { margin: 10px 0 21px; color: #f0ebe4; font-family: Georgia, serif; font-size: clamp(42px, 6.5vw, 72px); font-weight: 400; letter-spacing: -.06em; line-height: 1.05; }.welcome h1 em { color: #e0a17d; font-style: normal; }.welcome > p:not(.eyebrow) { max-width: 500px; margin: 0; color: #9a9e96; font-size: 14px; line-height: 1.8; }.composer-card { margin-top: 42px; padding: 18px; border: 1px solid rgba(255,255,255,.14); border-radius: 18px; background: rgba(55,58,55,.72); box-shadow: 0 20px 55px rgba(0,0,0,.12); }.composer-card textarea { display: block; width: 100%; resize: vertical; border: 0; outline: 0; color: #eee9e1; background: transparent; font-family: Georgia, serif; font-size: 18px; line-height: 1.7; }.composer-card textarea::placeholder { color: #747970; }.composer-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 12px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,.09); }.composer-footer span { color: #777d75; font-size: 11px; }.button:disabled { cursor: not-allowed; opacity: .45; }.error { color: #df9e86; font-size: 13px; }.promise-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-top: 64px; padding-top: 25px; border-top: 1px solid rgba(255,255,255,.09); }.promise-row div { display: grid; grid-template-columns: 23px 1fr; align-items: baseline; column-gap: 7px; }.promise-row span { color: #db9775; }.promise-row strong { color: #cbc6bc; font-family: Georgia, serif; font-size: 14px; font-weight: 400; }.promise-row small { grid-column: 2; margin-top: 5px; color: #777d75; font-size: 11px; }
@media (max-width: 650px) { .conversation-home { padding: 0 18px 45px; }.composer-footer { align-items: flex-start; flex-direction: column; gap: 13px; }.promise-row { grid-template-columns: 1fr; gap: 16px; } }
</style>
