<script setup lang="ts">
import { onMounted } from 'vue'
import { useWorkspaceStore } from './stores/workspace'

const workspace = useWorkspaceStore()

onMounted(() => {
  if (!workspace.ready) workspace.load()
})
</script>

<template>
  <RouterView />
</template>
