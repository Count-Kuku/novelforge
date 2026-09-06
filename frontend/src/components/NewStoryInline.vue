<script setup lang="ts">
import { ref } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'
import { api, ApiClientError } from '../api/client'
import type { CreationMode } from '../types'

const props = defineProps<{ defaultMode: CreationMode; heading?: string }>()
const emit = defineEmits<{ created: [story: Record<string, any>] }>()
const workspace = useWorkspaceStore()
const name = ref('')
const creating = ref(false)
const error = ref('')

async function submit() {
  if (!workspace.activeProjectId || !name.value.trim() || creating.value) return
  creating.value = true
  error.value = ''
  try {
    const data = await api.createStory(workspace.activeProjectId, {
      name: name.value.trim(),
      creation_mode: props.defaultMode,
    })
    const story = data.story
    await workspace.loadStories()
    await workspace.selectStory(story.story_id)
    name.value = ''
    emit('created', story)
  } catch (reason) {
    error.value = reason instanceof ApiClientError ? reason.message : '故事创建失败'
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="nsi-new-story">
    <p v-if="heading" class="nsi-heading">{{ heading }}</p>
    <div class="nsi-row">
      <input v-model="name" :placeholder="`新${defaultMode === 'conversational' ? '对话' : '规划'}故事名称`" aria-label="故事名称" @keydown.enter="submit" />
      <button class="nsi-create" :disabled="creating || !name.trim()" @click="submit">{{ creating ? '创建中…' : '创建并进入' }}</button>
    </div>
    <p v-if="error" class="nsi-error" role="status">{{ error }}</p>
  </div>
</template>

<style scoped>
.nsi-new-story { display: grid; gap: 8px; min-width: 0; }
.nsi-heading { margin: 0; color: var(--muted); font-size: 11px; line-height: 1.6; }
.nsi-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; }
.nsi-row input { min-width: 0; padding: 9px 11px; border: 1px solid var(--line); border-radius: 9px; outline: 0; color: inherit; background: transparent; font-size: 12px; }
.nsi-row input:focus-visible { border-color: color-mix(in srgb, var(--accent) 65%, transparent); }
.nsi-create { padding: 9px 13px; border: 0; border-radius: 9px; color: var(--paper-strong); background: var(--accent); font-size: 12px; white-space: nowrap; }
.nsi-create:hover { filter: brightness(1.06); }
.nsi-error { margin: 0; color: #b55f46; font-size: 11px; }
@media (max-width: 420px) { .nsi-row { grid-template-columns: 1fr; } }
</style>
