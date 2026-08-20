import { computed, ref } from 'vue'

const dirtyEditors = ref(new Set<string>())

export const hasDirtyEditors = computed(() => dirtyEditors.value.size > 0)

export function markEditorDirty(editorId: string) {
  const next = new Set(dirtyEditors.value)
  next.add(editorId)
  dirtyEditors.value = next
}

export function clearEditorDirty(editorId: string) {
  if (!dirtyEditors.value.has(editorId)) return
  const next = new Set(dirtyEditors.value)
  next.delete(editorId)
  dirtyEditors.value = next
}

export function clearAllEditorDirty() {
  if (dirtyEditors.value.size) dirtyEditors.value = new Set()
}
