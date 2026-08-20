<script setup lang="ts">
import { onMounted } from 'vue'
import { useWorkspaceStore } from './stores/workspace'
import AppDialogHost from './components/AppDialogHost.vue'
import AppNotificationHost from './components/AppNotificationHost.vue'

const workspace = useWorkspaceStore()

onMounted(() => {
  if (!workspace.ready) workspace.load()
})
</script>

<template>
  <RouterView />
  <AppDialogHost />
  <AppNotificationHost />
</template>
