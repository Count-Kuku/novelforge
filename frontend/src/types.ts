export type CreationMode = 'planned' | 'conversational'

export interface ProjectItem {
  project_id: string
  name: string
  title: string
  genre: string
  description: string
  updated_at: string
  story_count: number
}

export interface StoryItem {
  story_id: string
  name: string
  description: string
  status: string
  creation_mode: CreationMode
  created_at: string
  updated_at: string
  /** 当前故事是否仍处于迁移前的 legacy 读取模式。 */
  legacy_read_mode?: boolean
  legacy_migration_status?: 'required' | 'pending' | 'completed' | string
}

export interface StoryBranch {
  branch_id: string
  story_id?: string
  name: string
  parent_branch_id?: string | null
  fork_fragment_id?: string | null
  fork_checkpoint_id?: string | null
  head_checkpoint_id?: string | null
  status: 'active' | 'archived' | 'building' | 'failed' | string
  source_worldline_id?: string | null
  revision?: number
  fork_reason?: string | null
  created_at?: string
  updated_at?: string
  is_default?: boolean
}

export interface ReferenceLibrary {
  library_id: string
  project_name?: string
  title: string
  source_kind?: string
  source_id?: string | null
  status: 'active' | 'archived' | string
  latest_release_id?: string | null
  latest_release_no?: number | null
  release_status?: string
  updated_at?: string
}

export interface StoryLibraryBinding {
  binding_id: string
  story_id: string
  branch_id?: string | null
  library_id: string
  release_id: string
  status: 'preparing' | 'ready' | 'archived' | 'failed' | string
  library_title?: string
  release_no?: number
  links_count?: number
  changed_count?: number
  deleted_count?: number
  created_at?: string
  updated_at?: string
}

export interface LegacyReferenceStatus {
  story_id: string
  story_name?: string
  legacy_read_mode: boolean
  requires_confirmation: boolean
  story_knowledge_count?: number
  linked_copy_count?: number
  ready_binding_count?: number
  state?: { read_mode?: string; migration_status?: string }
}

export interface BootstrapData {
  projects: ProjectItem[]
  frontend_modes: CreationMode[]
}

export interface CreativeSession {
  session_id: string
  story_id: string
  title: string
  status: string
  session_goal: string
  auto_extract_mode: 'manual' | 'on_accept'
  active_fragment_id?: string
  updated_at: string
  branch_id?: string
  source_worldline_id?: string | null
}

export interface CreativeTurn {
  turn_id: string
  user_message: string
  status: string
  created_at: string
}

export interface CreativeFragment {
  fragment_id: string
  content: string
  status: string
  extraction_status?: 'not_started' | 'running' | 'completed' | 'failed'
  created_at: string
  branch_id?: string
  source_worldline_id?: string | null
}

export interface CreativeAction {
  action_id: string
  action_type: string
  status: string
  scope?: string
  target?: Record<string, unknown>
  plan?: Record<string, unknown>
  result?: Record<string, unknown>
  error_text?: string
  requires_confirmation?: boolean
  finished_at?: string
}
