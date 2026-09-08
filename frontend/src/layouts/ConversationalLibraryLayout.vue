<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="library-layout">
    <nav class="library-nav" aria-label="资料库分类">
      <RouterLink :to="{ name: 'conversational-library' }" exact-active-class="active"><span>⌂</span><strong>知识与资料</strong><small>搜索、审核与任务</small></RouterLink>
      <RouterLink :to="{ name: 'conversational-knowledge-entities' }" active-class="active"><span>◎</span><strong>实体与时间线</strong><small>角色、地点和事件</small></RouterLink>
      <RouterLink :to="{ name: 'conversational-knowledge-graph' }" active-class="active"><span>◇</span><strong>关系图</strong><small>查看知识关系</small></RouterLink>
      <RouterLink :to="{ name: 'conversational-research' }" active-class="active"><span>⌁</span><strong>导入资料</strong><small>粘贴资料、文件与处理状态</small></RouterLink>
    </nav>
    <RouterView />
  </div>
</template>

<style scoped>
.library-layout { padding: 24px clamp(22px, 5vw, 70px) 0; }.library-nav { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; max-width: 1120px; margin: 0 auto 28px; }.library-nav a { display: grid; grid-template-columns: 25px minmax(0,1fr); gap: 2px 8px; padding: 12px 13px; border: 1px solid var(--line); border-radius: 11px; color: var(--muted); background: rgba(255,255,255,.025); }.library-nav a.active { color: var(--ink); border-color: rgba(211,131,97,.4); background: rgba(211,131,97,.09); }.library-nav a > span { grid-row: 1 / 3; align-self: center; color: var(--accent); }.library-nav strong { font-size: 12px; font-weight: 500; }.library-nav small { overflow: hidden; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 820px) { .library-nav { grid-template-columns: repeat(2, minmax(0,1fr)); } }
@media (max-width: 520px) { .library-layout { padding-inline: 16px; }.library-nav { grid-template-columns: 1fr; } }
</style>
