<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { closeDialog, dialogState } from '../ui/dialog'

const inputValue = ref('')
const inputElement = ref<HTMLInputElement | null>(null)
const cancelElement = ref<HTMLButtonElement | null>(null)
const dialogElement = ref<HTMLFormElement | null>(null)
let returnFocus: HTMLElement | null = null

watch(dialogState, async (request) => {
  if (!request) {
    await nextTick()
    returnFocus?.focus()
    returnFocus = null
    return
  }
  returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  inputValue.value = request.input?.initialValue || ''
  await nextTick()
  if (request.input) {
    inputElement.value?.focus()
    inputElement.value?.select()
  } else {
    cancelElement.value?.focus()
  }
})

function canSubmit() {
  const input = dialogState.value?.input
  if (!input) return true
  const value = inputValue.value.trim()
  return Boolean(value) && (!input.match || value === input.match)
}

function submit() {
  if (!canSubmit()) return
  closeDialog(dialogState.value?.input ? inputValue.value.trim() : true)
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeDialog(null)
    return
  }
  if (event.key !== 'Tab' || !dialogElement.value) return
  const focusable = Array.from(dialogElement.value.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'))
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="dialogState" class="dialog-backdrop" @click.self="closeDialog(null)">
      <form ref="dialogElement" class="app-dialog" role="dialog" aria-modal="true" aria-labelledby="app-dialog-title" @submit.prevent="submit" @keydown="handleKeydown">
        <div class="dialog-heading">
          <span class="dialog-mark" :class="{ danger: dialogState.tone === 'danger' }">{{ dialogState.tone === 'danger' ? '!' : '·' }}</span>
          <div>
            <h2 id="app-dialog-title">{{ dialogState.title }}</h2>
            <p v-if="dialogState.message">{{ dialogState.message }}</p>
          </div>
        </div>
        <label v-if="dialogState.input" class="dialog-input">
          <span>{{ dialogState.input.label }}</span>
          <input ref="inputElement" v-model="inputValue" :placeholder="dialogState.input.placeholder" autocomplete="off" />
          <small v-if="dialogState.input.match">请输入“{{ dialogState.input.match }}”以确认。</small>
        </label>
        <div class="dialog-actions">
          <button ref="cancelElement" type="button" class="dialog-button secondary" @click="closeDialog(null)">{{ dialogState.cancelLabel || '取消' }}</button>
          <button type="submit" class="dialog-button" :class="{ danger: dialogState.tone === 'danger' }" :disabled="!canSubmit()">{{ dialogState.confirmLabel || '确认' }}</button>
        </div>
      </form>
    </div>
  </Teleport>
</template>

<style scoped>
.dialog-backdrop { position: fixed; z-index: 1000; inset: 0; display: grid; place-items: center; padding: 20px; background: rgba(25, 23, 21, .58); backdrop-filter: blur(4px); }
.app-dialog { width: min(440px, 100%); padding: 24px; border: 1px solid rgba(59, 48, 40, .16); border-radius: 18px; color: #302c28; background: #fffaf3; box-shadow: 0 28px 90px rgba(24, 20, 17, .28); }
.dialog-heading { display: grid; grid-template-columns: 34px 1fr; gap: 12px; align-items: start; }
.dialog-mark { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 9px; color: #7b553f; background: #f0e0d4; font-weight: 700; }
.dialog-mark.danger { color: #9a4137; background: #f9e0dc; }
.dialog-heading h2 { margin: 2px 0 0; font-family: Georgia, serif; font-size: 23px; font-weight: 500; }
.dialog-heading p { margin: 8px 0 0; color: #746b62; font-size: 13px; line-height: 1.65; }
.dialog-input { display: grid; gap: 7px; margin-top: 20px; color: #6b6259; font-size: 12px; }
.dialog-input input { width: 100%; padding: 11px 12px; border: 1px solid rgba(59, 48, 40, .18); border-radius: 9px; outline: none; color: #302c28; background: #fffdf9; }
.dialog-input input:focus { border-color: #a94b2f; box-shadow: 0 0 0 3px rgba(169, 75, 47, .12); }
.dialog-input small { color: #8e7f73; font-size: 11px; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 24px; }
.dialog-button { padding: 9px 15px; border: 1px solid #302c28; border-radius: 9px; color: #fffaf4; background: #302c28; }
.dialog-button.secondary { color: #5f574f; border-color: rgba(59, 48, 40, .15); background: transparent; }
.dialog-button.danger { border-color: #9a4137; background: #9a4137; }
.dialog-button:disabled { opacity: .45; }
</style>
