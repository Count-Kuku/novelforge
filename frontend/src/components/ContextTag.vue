<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'

type ContextTagItem = { value: string; label: string; description?: string; tone?: 'normal' | 'danger' }

const props = withDefaults(defineProps<{
  label?: string
  currentLabel: string
  items: ContextTagItem[]
  createLabel?: string
  emptyLabel?: string
  tone?: 'default' | 'accent'
}>(), { tone: 'default', emptyLabel: '暂无' })

const emit = defineEmits<{ select: [value: string]; create: [] }>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

function toggle() {
  open.value = !open.value
}

function pick(value: string) {
  open.value = false
  emit('select', value)
}

function createNew() {
  open.value = false
  emit('create')
}

function onDocMouseDown(event: MouseEvent) {
  if (!open.value || !root.value) return
  if (!root.value.contains(event.target as Node)) open.value = false
}

function onEsc(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}

if (typeof window !== 'undefined') {
  document.addEventListener('mousedown', onDocMouseDown)
  document.addEventListener('keydown', onEsc)
}
onBeforeUnmount(() => {
  if (typeof document !== 'undefined') {
    document.removeEventListener('mousedown', onDocMouseDown)
    document.removeEventListener('keydown', onEsc)
  }
})

const hasItems = computed(() => props.items.length > 0)
</script>

<template>
  <div class="ctx-tag" :class="['tone-' + tone, { open }]" ref="root">
    <button class="ctx-tag-button" type="button" :aria-expanded="open" :aria-haspopup="true" @click="toggle">
      <span v-if="label" class="ctx-tag-label">{{ label }}</span>
      <strong class="ctx-tag-current">{{ currentLabel || emptyLabel }}</strong>
      <i class="ctx-tag-caret" aria-hidden="true">▾</i>
    </button>
    <div v-if="open" class="ctx-tag-panel" role="listbox">
      <div v-if="!hasItems" class="ctx-tag-empty">{{ emptyLabel }}</div>
      <button
        v-for="item in items"
        :key="item.value"
        type="button"
        class="ctx-tag-item"
        :class="{ active: item.label === currentLabel, ['tone-' + (item.tone || 'normal')]: true }"
        role="option"
        :aria-selected="item.label === currentLabel"
        @click="pick(item.value)"
      >
        <span class="ctx-tag-item-label">{{ item.label }}</span>
        <small v-if="item.description">{{ item.description }}</small>
      </button>
      <button v-if="createLabel" type="button" class="ctx-tag-create" @click="createNew">
        <span aria-hidden="true">＋</span>{{ createLabel }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.ctx-tag { position: relative; display: inline-flex; min-width: 0; }
.ctx-tag-button { display: inline-flex; align-items: center; gap: 5px; min-width: 0; max-width: 100%; padding: 5px 8px; border: 1px solid rgba(255,255,255,.12); border-radius: 8px; color: #c9c2b6; background: transparent; font-family: inherit; font-size: 12px; line-height: 1.2; cursor: pointer; transition: border-color .12s, color .12s, background .12s; }
.ctx-tag-button:hover { color: #f0d8c4; border-color: rgba(222,172,139,.45); background: rgba(255,255,255,.03); }
.ctx-tag.open .ctx-tag-button { color: #f2eee7; border-color: rgba(222,172,139,.55); background: rgba(255,255,255,.05); }
.ctx-tag-label { color: #8a8f87; font-size: 10px; letter-spacing: .08em; text-transform: uppercase; }
.ctx-tag-current { min-width: 0; max-width: 220px; overflow: hidden; color: inherit; font-family: Georgia, serif; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.ctx-tag-caret { color: #7c8079; font-size: 9px; }
.ctx-tag-panel { position: absolute; top: calc(100% + 6px); left: 0; z-index: 30; min-width: 220px; max-height: 280px; overflow-y: auto; padding: 5px; border: 1px solid rgba(255,255,255,.14); border-radius: 11px; box-shadow: 0 14px 36px rgba(0,0,0,.32); background: #2d2f2d; }
.ctx-tag-empty { padding: 8px 10px; color: #8a8f87; font-size: 12px; }
.ctx-tag-item { display: grid; gap: 2px; width: 100%; padding: 7px 9px; border: 0; border-radius: 7px; color: #d9d3ca; background: transparent; font-family: inherit; text-align: left; cursor: pointer; }
.ctx-tag-item:hover { background: rgba(255,255,255,.06); color: #f0e9dd; }
.ctx-tag-item.active { background: rgba(211,131,97,.18); color: #f4d6c2; }
.ctx-tag-item small { color: #8a8f87; font-size: 10px; }
.ctx-tag-item.tone-danger { color: #d6a39a; }
.ctx-tag-create { display: flex; align-items: center; gap: 6px; width: 100%; padding: 7px 9px; margin-top: 4px; border-top: 1px dashed rgba(255,255,255,.14); border-radius: 0; color: #d38361; background: transparent; font-family: inherit; font-size: 12px; text-align: left; cursor: pointer; }
.ctx-tag-create:hover { color: #e8b89f; background: rgba(211,131,97,.08); }
</style>