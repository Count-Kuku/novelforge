<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useWorkspaceStore } from '../../stores/workspace'
import { api } from '../../api/client'

const workspace = useWorkspaceStore()
const hasStory = computed(() => Boolean(workspace.activeStory))
const profile = ref<Record<string, unknown>>({})
const profileLoading = ref(false)
const profileSaving = ref(false)
const profileMessage = ref('')
const discussionIdea = ref('')
const discussionText = ref('')
const discussionStep = ref<Record<string, any> | null>(null)
const discussing = ref(false)
const approving = ref(false)

async function loadProfile() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  profileLoading.value = true
  try {
    profile.value = (await api.profile(workspace.activeProjectId, workspace.activeStory.story_id)).profile || {}
  } catch {
    profile.value = {}
  } finally {
    profileLoading.value = false
  }
}

async function saveProfile() {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  profileSaving.value = true
  profileMessage.value = ''
  try {
    profile.value = (await api.updateProfile(workspace.activeProjectId, workspace.activeStory.story_id, profile.value)).profile
    profileMessage.value = '创作方向已保存'
  } catch (error) {
    profileMessage.value = error instanceof Error ? error.message : '保存失败'
  } finally {
    profileSaving.value = false
  }
}

function setProfileField(key: string, value: string | boolean) {
  profile.value = { ...profile.value, [key]: value }
}

async function discussProfile() {
  if (!workspace.activeProjectId || !workspace.activeStory || !discussionIdea.value.trim() || discussing.value) return
  discussing.value = true
  discussionText.value = ''
  try { await api.streamDiscussion(workspace.activeProjectId, workspace.activeStory.story_id, 'profile', discussionIdea.value.trim(), (event, data) => { if (event === 'delta') discussionText.value += String(data?.text || ''); if (event === 'done') discussionStep.value = data?.result || null }) } catch (error) { discussionText.value = error instanceof Error ? error.message : '讨论失败' } finally { discussing.value = false }
}

async function approveProfileDiscussion() {
  if (!workspace.activeProjectId || !workspace.activeStory || !discussionStep.value || approving.value) return
  approving.value = true
  try { const data = await api.approveDiscussion(workspace.activeProjectId, workspace.activeStory.story_id, 'profile', discussionStep.value); if ((data.result as any)?.saved_profile) profile.value = (data.result as any).saved_profile; discussionText.value = '创作方向讨论已批准并写入方向卡。' } catch (error) { discussionText.value = error instanceof Error ? error.message : '批准失败' } finally { approving.value = false }
}

onMounted(loadProfile)
</script>

<template>
  <section class="planned-page">
    <div class="page-lead"><div><p class="eyebrow">01 / CREATIVE DIRECTION</p><h2>先回答，<em>为什么是这个故事？</em></h2><p class="lead-copy">规划工作台把长篇创作拆成可以反复讨论的决定。这里是你的总控台，也是每一次写作前重新找回方向的地方。</p></div><div class="progress-ring"><strong>01</strong><span>/ 04</span><small>当前阶段</small></div></div>
    <div v-if="!hasStory" class="empty-panel"><span class="empty-icon">✦</span><h3>还没有故事</h3><p>连接 API 后，在这里创建你的第一个长篇故事。</p><button class="button accent">创建故事</button></div>
    <div v-else class="direction-grid">
      <article class="feature-card"><div class="feature-heading"><span class="number">A</span><div><p class="eyebrow">THE NORTH STAR</p><h3>一句话说清楚你的故事</h3></div></div><p>好的方向不是限制，而是当你迷路时，仍然知道哪条路属于这本书。</p><div class="quote-box">{{ workspace.activeStory?.description || '还没有写下故事简介。把你此刻最想写的那句话放进来。' }}</div><RouterLink to="/planned/outline" class="text-link">继续整理结构 <span>→</span></RouterLink></article>
      <article class="side-card"><p class="eyebrow">WORKSPACE NOTES</p><h3>一个安静的提醒</h3><p>规划模式不会替你决定故事。它只是把讨论、取舍和共识，留在下一次创作仍然找得到的地方。</p><div class="card-stamp">NF · 规划工作台</div></article>
      <article class="profile-card">
        <div class="profile-heading"><div><p class="eyebrow">CREATIVE PROFILE</p><h3>创作方向卡</h3></div><span v-if="profileMessage" class="saved-state">{{ profileMessage }}</span></div>
        <div v-if="profileLoading" class="profile-loading">正在读取创作方向…</div>
        <div v-else class="profile-form">
          <label>故事形态<input :value="String(profile.target_length || '')" placeholder="长篇" @input="setProfileField('target_length', ($event.target as HTMLInputElement).value)" /></label>
          <label>流程深度<input :value="String(profile.workflow_depth || '')" placeholder="完整长篇流程" @input="setProfileField('workflow_depth', ($event.target as HTMLInputElement).value)" /></label>
          <label class="profile-check"><input type="checkbox" :checked="Boolean(profile.allow_canon_deviation)" @change="setProfileField('allow_canon_deviation', ($event.target as HTMLInputElement).checked)" />允许创作时偏离已确认设定</label>
          <button class="button secondary" :disabled="profileSaving" @click="saveProfile">{{ profileSaving ? '保存中…' : '保存方向卡' }}</button>
        </div>
      </article>
      <article class="profile-discussion"><div><p class="eyebrow">DIRECTION DISCUSSION</p><h3>把方向说清楚，再交给结构。</h3></div><div class="profile-discussion-row"><input v-model="discussionIdea" placeholder="你想讨论目标读者、风格或流程中的哪一项？" @keydown.enter="discussProfile" /><button class="button secondary" :disabled="discussing || !discussionIdea.trim()" @click="discussProfile">{{ discussing ? '讨论中…' : '开始讨论' }}</button></div><div v-if="discussionText" class="profile-discussion-result"><p>{{ discussionText }}<span v-if="discussing">▌</span></p><button v-if="discussionStep" class="button accent" :disabled="approving" @click="approveProfileDiscussion">{{ approving ? '批准中…' : '批准并应用' }}</button></div></article>
    </div>
  </section>
</template>

<style scoped>
.planned-page { max-width: 1180px; margin: 0 auto; }.page-lead { display: flex; align-items: flex-end; justify-content: space-between; gap: 40px; margin-bottom: 44px; }.page-lead h2 { max-width: 700px; margin: 0; font-family: Georgia, serif; font-size: clamp(35px, 4.6vw, 61px); font-weight: 400; letter-spacing: -.055em; line-height: 1.1; }.page-lead h2 em { color: var(--accent); font-style: normal; }.lead-copy { max-width: 540px; margin: 22px 0 0; color: #897e73; font-size: 14px; line-height: 1.8; }.progress-ring { display: grid; grid-template-columns: auto auto; align-items: baseline; width: 106px; height: 106px; padding: 28px 16px 0; border: 1px solid #dbc9b9; border-radius: 50%; color: #b06749; transform: rotate(-12deg); }.progress-ring strong { font-family: Georgia, serif; font-size: 28px; font-weight: 400; }.progress-ring span { margin-left: 3px; color: #ae9d8f; font-size: 12px; }.progress-ring small { grid-column: 1 / -1; margin-top: -3px; color: #a39283; font-size: 10px; transform: rotate(12deg); }.direction-grid { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(250px, .75fr); gap: 20px; }.feature-card, .side-card, .profile-card, .empty-panel { border: 1px solid var(--line); border-radius: 23px; background: rgba(255,253,249,.72); }.feature-card { min-height: 380px; padding: 32px; }.feature-heading { display: flex; gap: 16px; align-items: flex-start; }.number { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; color: #a75b3f; background: #f1ded4; font-family: Georgia, serif; }.feature-heading h3 { margin: 2px 0 0; font-family: Georgia, serif; font-size: 25px; font-weight: 400; }.feature-card > p { max-width: 500px; margin: 38px 0 17px; color: #8b8175; font-size: 14px; line-height: 1.7; }.quote-box { padding: 21px 23px; border-left: 3px solid #cd805f; border-radius: 2px 12px 12px 2px; color: #60554b; background: #f7efe5; font-family: Georgia, serif; font-size: 16px; line-height: 1.7; }.text-link { display: inline-flex; gap: 12px; margin-top: 24px; color: #a95c40; font-size: 13px; }.text-link span { font-size: 18px; }.side-card { display: flex; min-height: 380px; flex-direction: column; padding: 28px; background: #e9e1d6; }.side-card h3 { margin: 20px 0 14px; font-family: Georgia, serif; font-size: 26px; font-weight: 400; }.side-card > p:not(.eyebrow) { margin: 0; color: #766c61; font-size: 14px; line-height: 1.8; }.card-stamp { margin-top: auto; color: #a59685; font-size: 11px; letter-spacing: .1em; }.profile-card { grid-column: 1 / -1; padding: 26px 30px; background: #fffaf4; }.profile-heading, .profile-form { display: flex; align-items: center; justify-content: space-between; gap: 16px; }.profile-heading h3 { margin: 4px 0 0; font-family: Georgia, serif; font-size: 24px; font-weight: 400; }.profile-form { align-items: end; margin-top: 22px; }.profile-form label { display: grid; gap: 6px; color: #8a7a6e; font-size: 11px; }.profile-form input:not([type='checkbox']) { width: 190px; padding: 9px 10px; border: 1px solid #e8d3c3; border-radius: 8px; outline: 0; color: #534940; background: #fffdf9; }.profile-check { display: flex !important; align-items: center; gap: 7px; }.profile-check input { accent-color: #b86c4d; }.saved-state { color: #778d72; font-size: 12px; }.profile-loading { padding: 25px 0 3px; color: #9a8c7f; font-size: 12px; }
.empty-panel { padding: 72px 30px; text-align: center; }.empty-icon { display: block; margin-bottom: 15px; color: var(--accent); font-size: 31px; }.empty-panel h3 { margin: 0; font-family: Georgia, serif; font-size: 25px; font-weight: 400; }.empty-panel p { color: var(--muted); font-size: 13px; }
@media (max-width: 760px) { .page-lead { align-items: flex-start; }.progress-ring { display: none; }.direction-grid { grid-template-columns: 1fr; }.feature-card, .side-card { min-height: 300px; padding: 24px; }.profile-form { align-items: stretch; flex-direction: column; }.profile-form input:not([type='checkbox']) { width: 100%; } }
</style>

<style scoped>
.profile-discussion { grid-column: 1 / -1; display: grid; gap: 14px; padding: 26px 30px; border: 1px solid #dfcfbe; border-radius: 18px; background: #f5eee5; }.profile-discussion h3 { margin: 4px 0 0; font-family: Georgia, serif; font-size: 23px; font-weight: 400; }.profile-discussion-row { display: flex; gap: 8px; }.profile-discussion-row input { flex: 1; min-width: 0; padding: 10px 12px; border: 1px solid #e6d5c6; border-radius: 8px; outline: 0; color: #544940; background: #fffdf9; }.profile-discussion-result { padding: 14px; border-radius: 10px; color: #66594e; background: #eee1d4; font-size: 13px; line-height: 1.7; }.profile-discussion-result p { margin: 0 0 10px; }
</style>
