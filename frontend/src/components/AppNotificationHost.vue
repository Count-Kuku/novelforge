<script setup lang="ts">
import { dismissNotification, notifications } from '../ui/notifications'
</script>

<template>
  <Teleport to="body">
    <div class="notification-stack" aria-live="polite" aria-atomic="false">
      <button v-for="item in notifications" :key="item.id" class="app-notification" :class="item.tone" @click="dismissNotification(item.id)">
        <span>{{ item.tone === 'success' ? '✓' : item.tone === 'error' ? '!' : 'i' }}</span>
        {{ item.message }}
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.notification-stack { position: fixed; z-index: 1100; top: 20px; right: 20px; display: grid; width: min(360px, calc(100vw - 40px)); gap: 8px; pointer-events: none; }
.app-notification { display: grid; grid-template-columns: 22px 1fr; align-items: center; gap: 9px; width: 100%; padding: 12px 14px; border: 1px solid rgba(58, 48, 39, .15); border-radius: 11px; color: #423b35; background: #fffaf3; box-shadow: 0 12px 35px rgba(31, 25, 21, .18); pointer-events: auto; text-align: left; }
.app-notification span { display: grid; place-items: center; width: 20px; height: 20px; border-radius: 6px; color: #6a5d52; background: #eee6dc; font-size: 11px; font-weight: 700; }
.app-notification.success span { color: #557250; background: #e4efe1; }
.app-notification.error span { color: #99453b; background: #f7e1dc; }
@media (max-width: 520px) { .notification-stack { top: 12px; right: 12px; width: calc(100vw - 24px); } }
</style>
