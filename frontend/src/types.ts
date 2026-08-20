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
  updated_at: string
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
  created_at: string
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
