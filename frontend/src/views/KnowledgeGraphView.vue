<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'

const workspace = useWorkspaceStore()
const graph = ref<{ nodes?: any[]; edges?: any[] }>({})
const loading = ref(true)
const error = ref('')

async function loadGraph() {
  if (!workspace.activeProjectId) { loading.value = false; return }
  loading.value = true
  try { graph.value = await api.knowledgeGraph(workspace.activeProjectId, workspace.activeStory?.story_id) as typeof graph.value } catch (reason) { error.value = reason instanceof ApiClientError ? reason.message : '无法读取关系图' } finally { loading.value = false }
}

onMounted(loadGraph)
</script>

<template>
  <section class="graph-page"><div class="graph-heading"><div><p class="eyebrow">关系图</p><h1>查看正式知识中的<em>实体关系</em></h1><p>关系图按当前故事生成。关系的增删和修改仍通过对应知识条目完成。</p></div><button class="button secondary" :disabled="loading" @click="loadGraph">{{ loading ? '读取中…' : '刷新关系图' }}</button></div><div v-if="loading" class="graph-state">正在读取关系…</div><p v-else-if="error" class="graph-error">{{ error }}</p><div v-else class="graph-grid"><article><p class="eyebrow">节点 · {{ graph.nodes?.length || 0 }}</p><div v-if="!graph.nodes?.length" class="muted">当前故事还没有关系节点。</div><div v-for="node in graph.nodes || []" :key="node.node_id || node.id" class="graph-node"><strong>{{ node.label || node.name || node.node_id }}</strong><small>{{ node.node_type || node.type || '实体' }}</small></div></article><article><p class="eyebrow">关系 · {{ graph.edges?.length || 0 }}</p><div v-if="!graph.edges?.length" class="muted">当前故事还没有关系记录。</div><div v-for="edge in graph.edges || []" :key="edge.edge_id || `${edge.source_id}-${edge.target_id}`" class="graph-edge"><span>{{ edge.source_label || edge.source_id }}</span><b>{{ edge.relation_type || edge.label || '关联' }}</b><span>{{ edge.target_label || edge.target_id }}</span></div></article></div></section>
</template>

<style scoped>
.graph-page { max-width: 1100px; margin: 0 auto; padding: 12px 0 60px; }.graph-heading { display: flex; align-items: end; justify-content: space-between; gap: 22px; margin-bottom: 38px; }.graph-heading h1 { max-width: 720px; margin: 10px 0 16px; font-family: Georgia, serif; font-size: clamp(36px, 5vw, 62px); font-weight: 400; letter-spacing: -.055em; line-height: 1.08; }.graph-heading h1 em { color: var(--accent); font-style: normal; }.graph-heading p:not(.eyebrow) { max-width: 570px; color: var(--muted); font-size: 13px; line-height: 1.8; }.graph-state { min-height: 220px; display: grid; place-items: center; color: var(--muted); font-size: 13px; }.graph-error { color: #c67862; font-size: 13px; }.graph-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }.graph-grid article { min-height: 240px; padding: 22px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,255,255,.05); }.graph-node, .graph-edge { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; border-top: 1px solid var(--line); }.graph-node strong { color: inherit; font-family: Georgia, serif; font-size: 15px; font-weight: 400; }.graph-node small { color: var(--muted); font-size: 10px; }.graph-edge { color: var(--muted); font-size: 11px; }.graph-edge b { color: var(--accent); font-weight: 500; }.muted { color: var(--muted); font-size: 12px; }
@media (max-width: 700px) { .graph-heading { align-items: flex-start; flex-direction: column; }.graph-grid { grid-template-columns: 1fr; } }
</style>
