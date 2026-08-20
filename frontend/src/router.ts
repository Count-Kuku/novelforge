import { createRouter, createWebHistory } from 'vue-router'
import ModePickerView from './views/ModePickerView.vue'
import PlannedDirectionView from './views/planned/PlannedDirectionView.vue'
import PlannedOutlineView from './views/planned/PlannedOutlineView.vue'
import PlannedChaptersView from './views/planned/PlannedChaptersView.vue'
import ConversationalHomeView from './views/conversational/ConversationalHomeView.vue'
import ConversationalSessionView from './views/conversational/ConversationalSessionView.vue'
import ComponentPreviewView from './views/ComponentPreviewView.vue'
import SharedWorkspaceView from './views/SharedWorkspaceView.vue'
import SettingsView from './views/SettingsView.vue'
import PlannedStructureAssetView from './views/planned/PlannedStructureAssetView.vue'
import KnowledgeGraphView from './views/KnowledgeGraphView.vue'
import ResearchView from './views/ResearchView.vue'
import RulesView from './views/RulesView.vue'
import KnowledgeEntitiesView from './views/KnowledgeEntitiesView.vue'
import ContentBrowserView from './views/ContentBrowserView.vue'
import KnowledgeEditorView from './views/KnowledgeEditorView.vue'
import { useWorkspaceStore } from './stores/workspace'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'mode-picker', component: ModePickerView },
    { path: '/components', name: 'components', component: ComponentPreviewView },
    {
      path: '/planned',
      component: () => import('./layouts/PlannedAppLayout.vue'),
      children: [
        { path: '', name: 'planned-home', component: PlannedDirectionView },
        { path: 'direction', name: 'planned-direction', component: PlannedDirectionView },
        { path: 'outline', name: 'planned-outline', component: PlannedOutlineView },
        { path: 'chapters', name: 'planned-chapters', component: PlannedChaptersView },
        { path: 'volumes/:assetNo', name: 'planned-volume', component: PlannedStructureAssetView, meta: { assetType: 'volume' } },
        { path: 'arcs/:assetNo', name: 'planned-arc', component: PlannedStructureAssetView, meta: { assetType: 'arc' } },
        { path: 'workspace', name: 'planned-workspace', component: SharedWorkspaceView },
        { path: 'workspace/graph', name: 'planned-knowledge-graph', component: KnowledgeGraphView },
        { path: 'workspace/entities', name: 'planned-knowledge-entities', component: KnowledgeEntitiesView },
        { path: 'workspace/content', name: 'planned-content', component: ContentBrowserView },
        { path: 'workspace/knowledge/:recordType/:recordId', name: 'planned-knowledge-editor', component: KnowledgeEditorView },
        { path: 'workspace/research', name: 'planned-research', component: ResearchView },
        { path: 'settings', name: 'planned-settings', component: SettingsView },
        { path: 'rules', name: 'planned-rules', component: RulesView },
      ],
    },
    {
      path: '/conversational',
      component: () => import('./layouts/ConversationalAppLayout.vue'),
      children: [
        { path: '', name: 'conversational-home', component: ConversationalHomeView },
        { path: 'session/:sessionId', name: 'conversational-session', component: ConversationalSessionView },
        { path: 'workspace', name: 'conversational-workspace', component: SharedWorkspaceView },
        { path: 'workspace/graph', name: 'conversational-knowledge-graph', component: KnowledgeGraphView },
        { path: 'workspace/entities', name: 'conversational-knowledge-entities', component: KnowledgeEntitiesView },
        { path: 'workspace/content', name: 'conversational-content', component: ContentBrowserView },
        { path: 'workspace/knowledge/:recordType/:recordId', name: 'conversational-knowledge-editor', component: KnowledgeEditorView },
        { path: 'workspace/research', name: 'conversational-research', component: ResearchView },
        { path: 'settings', name: 'conversational-settings', component: SettingsView },
        { path: 'rules', name: 'conversational-rules', component: RulesView },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  if (to.name === 'mode-picker' || to.name === 'components') return true
  const workspace = useWorkspaceStore()
  if (!workspace.ready) await workspace.load()
  const requestedMode = to.path.startsWith('/conversational') ? 'conversational' : 'planned'
  if (workspace.activeStory && workspace.mode !== requestedMode) {
    return workspace.mode === 'conversational' ? '/conversational' : '/planned'
  }
  return true
})
