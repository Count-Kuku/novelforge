<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'
import { dialog } from '../ui/dialog'
import { notify } from '../ui/notifications'

const workspace = useWorkspaceStore()
const items = ref<any[]>([])
const nextCursor = ref('')
const loading = ref(false)
const error = ref('')
const total = ref(0)

async function load(cursor = '') {
  if (!workspace.activeProjectId || !workspace.activeStory) return
  loading.value = true
  try { const data = await api.content(workspace.activeProjectId, workspace.activeStory.story_id, cursor); items.value = cursor ? [...items.value, ...data.items] : data.items; nextCursor.value = data.next_cursor || ''; total.value = data.total || items.value.length } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '内容列表读取失败' } finally { loading.value = false }
}

async function remove(item: any) {
  if (!workspace.activeProjectId || !workspace.activeStory || !item?.deletable) return
  if (!await dialog.confirm({ title: '删除这项内容？', message: `“${item.label || item.path_label}”将按其资源类型执行删除。`, confirmLabel: '删除', tone: 'danger' })) return
  try { await api.deleteContent(workspace.activeProjectId, item, workspace.activeStory.story_id); items.value = items.value.filter((candidate) => candidate.id !== item.id); notify('内容已删除', 'success') } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '删除内容失败' }
}

onMounted(() => load())
</script>

<template>
  <section class="content-page"><p class="eyebrow">内容浏览</p><h1>查看当前故事的<em>全部内容</em></h1><p class="intro">按类型浏览结构、大纲、章节、来源和运行记录。只有明确标记为可删除的内容会显示删除按钮。</p><div class="content-meta"><span>共 {{ total }} 项</span><button class="button secondary" :disabled="loading" @click="load()">刷新</button></div><div v-if="loading && !items.length" class="content-state">正在读取内容…</div><div v-else class="content-list"><article v-for="item in items" :key="item.id" class="content-row"><div><p class="eyebrow">{{ item.group }}</p><h2>{{ item.label || item.path_label }}</h2><p>{{ item.path_label }}</p></div><button v-if="item.deletable" class="link-button danger" @click="remove(item)">删除</button></article><button v-if="nextCursor" class="button secondary" :disabled="loading" @click="load(nextCursor)">{{ loading ? '加载中…' : '加载更多' }}</button></div><p v-if="!loading && !items.length" class="content-state">当前故事还没有可浏览内容。</p><p v-if="error" class="content-error">{{ error }}</p></section>
</template>

<style scoped>
.content-page { max-width: 1080px; margin: 0 auto; padding: 12px 0 60px; }.content-page h1 { max-width: 760px; margin: 10px 0 16px; font-family: Georgia, serif; font-size: clamp(36px, 5vw, 62px); font-weight: 400; letter-spacing: -.055em; line-height: 1.08; }.content-page h1 em { color: var(--accent); font-style: normal; }.intro { max-width: 650px; color: var(--muted); font-size: 13px; line-height: 1.8; }.content-meta { display: flex; align-items: center; justify-content: space-between; margin: 28px 0 12px; color: var(--muted); font-size: 11px; }.content-list { display: grid; gap: 8px; }.content-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px; border: 1px solid var(--line); border-radius: 12px; background: rgba(255,255,255,.05); }.content-row h2 { margin: 5px 0; font-family: Georgia, serif; font-size: 18px; font-weight: 400; }.content-row p:not(.eyebrow) { margin: 0; color: var(--muted); font-size: 11px; }.link-button { border: 0; color: #b55f46; background: transparent; cursor: pointer; font-size: 11px; }.content-state { min-height: 200px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }.content-error { color: #d18d82; font-size: 12px; }
</style>
