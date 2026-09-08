import type {
  BootstrapData,
  CreationMode,
  CreativeSession,
  CreativeFragment,
  CreativeAction,
  CreativeTurn,
  ProjectItem,
  StoryItem,
  StoryBranch,
  ReferenceLibrary,
  StoryLibraryBinding,
  LegacyReferenceStatus,
} from '../types'

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) || '/api/v1'

function requestId(): string {
  return globalThis.crypto?.randomUUID?.() || `nf_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

export class ApiClientError extends Error {
  code: string
  status: number

  constructor(message: string, status: number, code = 'request_failed') {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.code = code
  }
}

type Envelope<T> = { data: T; meta?: Record<string, unknown> }
type RequestOptions = RequestInit & { timeoutMs?: number }

const DEFAULT_REQUEST_TIMEOUT_MS = 20_000
const MATERIAL_UPLOAD_TIMEOUT_MS = 300_000

async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const { timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS, ...requestInit } = init
  const method = (requestInit.method || 'GET').toUpperCase()
  const controller = new AbortController()
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs)
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...requestInit,
      signal: requestInit.signal || controller.signal,
      headers: {
        Accept: 'application/json',
        'X-Request-Id': requestId(),
        ...(requestInit.body && !(requestInit.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...(method !== 'GET' && method !== 'HEAD' ? { 'X-NovelForge-Client': 'vue', 'Idempotency-Key': requestId() } : {}),
        ...(requestInit.headers || {}),
      },
    })
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === 'AbortError') throw new ApiClientError('请求超时或已取消', 408, 'request_aborted')
    throw reason
  } finally {
    globalThis.clearTimeout(timeout)
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = payload?.error || {}
    throw new ApiClientError(error.message || `请求失败（${response.status}）`, response.status, error.code)
  }
  return (payload as Envelope<T>).data ?? (payload as T)
}

function knowledgeScopeQuery(storyId?: string, branchId?: string): string {
  const params = new URLSearchParams()
  if (storyId) params.set('story_id', storyId)
  if (branchId) params.set('branch_id', branchId)
  const encoded = params.toString()
  return encoded ? `?${encoded}` : ''
}

type OperationEvent = { id?: number; event: string; data: any }

async function replayOperationEvents(
  operationId: string,
  after: number,
  onEvent: (event: string, data: any) => void,
): Promise<{ cursor: number; terminal: boolean }> {
  const payload = await request<{ operation_id: string; events: OperationEvent[] }>(
    `/operations/${encodeURIComponent(operationId)}/events?after=${Math.max(0, after)}`,
  )
  let cursor = after
  let terminal = false
  for (const item of payload.events || []) {
    const sequence = Number(item.id || 0)
    if (sequence > cursor) cursor = sequence
    onEvent(String(item.event || 'message'), item.data || {})
    if (['done', 'error', 'cancelled'].includes(String(item.event || ''))) terminal = true
  }
  return { cursor, terminal }
}

async function streamSse(
  path: string,
  init: RequestInit,
  onEvent: (event: string, data: any) => void,
  label: string,
): Promise<void> {
  let operationId = ''
  let cursor = 0
  let lastError: unknown = new ApiClientError(`${label}连接意外结束`, 499, 'stream_disconnected')
  let reconnectAttempt = 0
  const recoveryDeadline = Date.now() + 120_000

  while (true) {
    if (operationId) {
      try {
        const replay = await replayOperationEvents(operationId, cursor, onEvent)
        cursor = replay.cursor
        if (replay.terminal) return
      } catch (reason) {
        lastError = reason
      }
      if (Date.now() >= recoveryDeadline) throw lastError
      reconnectAttempt += 1
      await new Promise((resolve) => globalThis.setTimeout(resolve, Math.min(300 * reconnectAttempt, 2_000)))
      continue
    }
    try {
      const response = await fetch(`${API_BASE}${path}`, init)
      if (!response.ok || !response.body) {
        const body = await response.json().catch(() => ({}))
        throw new ApiClientError(body?.error?.message || `${label}请求失败（${response.status}）`, response.status, body?.error?.code)
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let terminal = false
      while (true) {
        const { done, value } = await reader.read()
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
        const frames = buffer.split('\n\n')
        buffer = frames.pop() || ''
        for (const frame of frames) {
          const event = frame.match(/^event:\s*(.+)$/m)?.[1] || 'message'
          const raw = frame.match(/^data:\s*(.+)$/m)?.[1] || '{}'
          const sequence = Number(frame.match(/^id:\s*(\d+)$/m)?.[1] || 0)
          if (sequence > cursor) cursor = sequence
          const data = JSON.parse(raw)
          if (data?.operation_id) operationId = String(data.operation_id)
          onEvent(event, data)
          if (['done', 'error', 'cancelled'].includes(event)) terminal = true
        }
        if (done) break
      }
      if (terminal) return
      lastError = new ApiClientError(`${label}连接意外结束，正在恢复`, 499, 'stream_disconnected')
    } catch (reason) {
      lastError = reason
      if (!operationId) throw reason
    }
    if (!operationId) throw lastError
    if (Date.now() >= recoveryDeadline) throw lastError
    reconnectAttempt += 1
    await new Promise((resolve) => globalThis.setTimeout(resolve, Math.min(300 * reconnectAttempt, 2_000)))
  }
}

export const api = {
  bootstrap: () => request<BootstrapData>('/bootstrap'),
  createProject: (payload: { name: string; title?: string; genre?: string; description?: string }) =>
    request<{ project: ProjectItem }>('/projects', { method: 'POST', body: JSON.stringify(payload) }),
  renameProject: (projectId: string, name: string) => request<{ project: ProjectItem }>(`/projects/${encodeURIComponent(projectId)}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteProject: (projectId: string) => request<{ deleted: boolean }>(`/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' }),
  createStory: (projectId: string, payload: { name: string; description?: string; creation_mode: CreationMode }) =>
    request<{ story: StoryItem }>(`/projects/${encodeURIComponent(projectId)}/stories`, { method: 'POST', body: JSON.stringify(payload) }),
  stories: (projectId: string) => request<{ stories: StoryItem[] }>(`/projects/${encodeURIComponent(projectId)}/stories`),
  branches: (projectId: string, storyId: string, includeArchived = false) =>
    request<{ branches: StoryBranch[]; active_branch_id?: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/branches${includeArchived ? '?include_archived=true' : ''}`),
  branch: (projectId: string, storyId: string, branchId: string) =>
    request<{ branch: StoryBranch; context?: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/branches/${encodeURIComponent(branchId)}`),
  createBranch: (projectId: string, storyId: string, payload: { name: string; description?: string; parent_branch_id?: string; fork_fragment_id?: string; fork_checkpoint_id?: string; allow_current_state?: boolean }) =>
    request<{ branch: StoryBranch; session?: CreativeSession; context?: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/branches`, { method: 'POST', body: JSON.stringify(payload) }),
  updateBranch: (projectId: string, storyId: string, branchId: string, patch: { name?: string; description?: string; status?: 'active' | 'archived' }) =>
    request<{ branch: StoryBranch }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/branches/${encodeURIComponent(branchId)}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  forkBranch: (projectId: string, storyId: string, branchId: string, payload: { name: string; description?: string; fork_fragment_id?: string; fork_checkpoint_id?: string; allow_current_state?: boolean }) =>
    request<{ branch: StoryBranch; session?: CreativeSession; context?: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/branches/${encodeURIComponent(branchId)}/fork`, { method: 'POST', body: JSON.stringify(payload) }),
  createBranchCheckpoint: (projectId: string, storyId: string, branchId: string, payload: { frontier_fragment_id?: string; extraction_status: 'ready' | 'completed' | 'skipped' | 'pending'; reason?: string }) =>
    request<{ checkpoint: { checkpoint_id: string; extraction_status?: string; frontier_fragment_id?: string } }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/branches/${encodeURIComponent(branchId)}/checkpoints`, { method: 'POST', body: JSON.stringify(payload) }),
  referenceLibraries: (projectId: string, includeArchived = false) =>
    request<{ libraries: ReferenceLibrary[] }>(`/projects/${encodeURIComponent(projectId)}/reference-libraries${includeArchived ? '?include_archived=true' : ''}`),
  archiveReferenceLibrary: (projectId: string, libraryId: string) =>
    request<{ archived: boolean; library_id: string }>(`/projects/${encodeURIComponent(projectId)}/reference-libraries/${encodeURIComponent(libraryId)}/archive`, { method: 'POST' }),
  referenceLibraryReleases: (projectId: string, libraryId: string) =>
    request<{ releases: Array<Record<string, unknown>> }>(`/projects/${encodeURIComponent(projectId)}/reference-libraries/${encodeURIComponent(libraryId)}/releases`),
  referenceLibraryReleaseSources: (projectId: string, libraryId: string, releaseId: string, sourceId?: string) =>
    request<{ library_id: string; release_id: string; sources: Array<Record<string, unknown>> }>(`/projects/${encodeURIComponent(projectId)}/reference-libraries/${encodeURIComponent(libraryId)}/releases/${encodeURIComponent(releaseId)}/sources${sourceId ? `?source_id=${encodeURIComponent(sourceId)}` : ''}`),
  storyReferenceLibraries: (projectId: string, storyId: string, branchId?: string, includeArchived = false) => {
    const query = branchId || includeArchived ? `?${branchId ? `branch_id=${encodeURIComponent(branchId)}` : ''}${branchId && includeArchived ? '&' : ''}${includeArchived ? 'include_archived=true' : ''}` : ''
    return request<{ bindings: StoryLibraryBinding[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/reference-libraries${query}`)
  },
  bindReferenceLibrary: (projectId: string, storyId: string, libraryId: string, payload: { release_id: string; branch_id?: string; idempotency_key?: string }) =>
    request<{ binding: StoryLibraryBinding }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/reference-libraries/${encodeURIComponent(libraryId)}/bindings`, { method: 'POST', body: JSON.stringify(payload) }),
  unbindReferenceLibrary: (projectId: string, storyId: string, bindingId: string, branchId?: string) =>
    request<{ binding: StoryLibraryBinding; unbound: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/reference-libraries/bindings/${encodeURIComponent(bindingId)}${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`, { method: 'DELETE' }),
  referenceContext: (projectId: string, storyId: string, branchId?: string) =>
    request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/reference-context${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`),
  legacyReferenceStatus: (projectId: string, storyId: string) =>
    request<LegacyReferenceStatus>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/legacy-reference-status`),
  migrateLegacyReference: (projectId: string, storyId: string, payload: { selections: Array<{ library_id: string; release_id: string; branch_id?: string }>; confirmed: true }) =>
    request<{ story_id: string; bindings: StoryLibraryBinding[]; legacy_migration: boolean; state?: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/legacy-reference-migration`, { method: 'POST', body: JSON.stringify(payload) }),
  renameStory: (projectId: string, storyId: string, name: string, description?: string) => request<{ story: StoryItem }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}`, { method: 'PATCH', body: JSON.stringify({ name, description }) }),
  copyStory: (projectId: string, storyId: string, payload: { name: string; include_discussions?: boolean; include_summaries?: boolean; include_chapters?: boolean }) =>
    request<{ story: StoryItem }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/copy`, { method: 'POST', body: JSON.stringify(payload) }),
  archiveStory: (projectId: string, storyId: string) => request<{ archived: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/archive`, { method: 'POST' }),
  restoreStory: (projectId: string, storyId: string) => request<{ restored: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/restore`, { method: 'POST' }),
  deleteStory: (projectId: string, storyId: string) => request<{ deleted: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}`, { method: 'DELETE' }),
  setStoryMode: (projectId: string, storyId: string, creationMode: CreationMode) =>
    request<{ story: StoryItem }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/mode`, {
      method: 'PATCH',
      body: JSON.stringify({ creation_mode: creationMode }),
    }),
  profile: (projectId: string, storyId: string, branchId?: string) =>
    request<{ profile: Record<string, unknown>; branch_id?: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/profile${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`),
  updateProfile: (projectId: string, storyId: string, profile: Record<string, unknown>, branchId?: string) =>
    request<{ profile: Record<string, unknown>; saved: boolean; branch_id?: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/profile${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`, {
      method: 'PUT',
      body: JSON.stringify({ profile }),
    }),
  discussionArtifact: (projectId: string, storyId: string, assetType: 'profile' | 'outline' | 'volume' | 'arc' | 'chapter', assetNo?: number, branchId?: string) => {
    const query = new URLSearchParams()
    if (assetNo) query.set('asset_no', String(assetNo))
    if (branchId) query.set('branch_id', branchId)
    return request<{ asset_type: string; artifact: Record<string, unknown>; branch_id?: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/discussions/${assetType}${query.toString() ? `?${query}` : ''}`)
  },
  approveDiscussion: (projectId: string, storyId: string, assetType: 'profile' | 'outline' | 'volume' | 'arc' | 'chapter', step: Record<string, unknown>, assetNo?: number, branchId?: string) => {
    const query = new URLSearchParams()
    if (assetNo) query.set('asset_no', String(assetNo))
    if (branchId) query.set('branch_id', branchId)
    return request<{ asset_type: string; result: unknown; branch_id?: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/discussions/${assetType}/approve${query.toString() ? `?${query}` : ''}`, { method: 'POST', body: JSON.stringify({ step, ...(branchId ? { branch_id: branchId } : {}) }) })
  },
  capabilities: () => request<{ capabilities: Record<string, { available: boolean; status: string; message: string; provider?: string }> }>('/capabilities'),
  developerSettings: () => request<{ enabled: boolean; projections: string[] }>('/settings/developer'),
  operationEvents: (operationId: string, after = 0) => request<{ operation_id: string; events: OperationEvent[] }>(`/operations/${encodeURIComponent(operationId)}/events?after=${Math.max(0, after)}`),
  cancelOperation: (operationId: string) => request<{ operation_id: string; status: string }>(`/operations/${encodeURIComponent(operationId)}/cancel`, { method: 'POST', body: '{}' }),
  usage: (projectId?: string, storyId?: string) => request<{ today: Record<string, unknown>; month: Record<string, unknown>; daily: unknown[]; recent: unknown[] }>(`/usage${projectId ? `?project_id=${encodeURIComponent(projectId)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}` : ''}`),
  usageBreakdown: (dimension: 'project' | 'story' | 'model' | 'operation' | 'agent', projectId?: string, storyId?: string) => request<{ dimension: string; rows: Record<string, unknown>[] }>(`/usage/breakdown?dimension=${encodeURIComponent(dimension)}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ''}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}`),
  modelProfiles: () => request<{ active_profile_id: string; profiles: Record<string, unknown>[] }>('/settings/models'),
  updateModelProfile: (profile: Record<string, unknown>) => request<{ profile: Record<string, unknown>; saved: boolean }>('/settings/models', { method: 'PUT', body: JSON.stringify(profile) }),
  discoverModels: (baseUrl: string, apiKey: string, providerType: string) =>
    request<{ base_url: string; provider_hint: string; models: Array<{ id: string; context_window: number; multimodal: boolean; native_web_search: boolean; provider_hint: string }> }>('/settings/models/discover', { method: 'POST', body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, provider_type: providerType }) }),
  activateModelProfile: (profileId: string) => request<{ profile: Record<string, unknown>; active_profile_id: string }>('/settings/models/active', { method: 'POST', body: JSON.stringify({ profile_id: profileId }) }),
  settingsRules: (projectId?: string, storyId?: string, branchId?: string) => request<{ global: Record<string, unknown>; project: Record<string, unknown>; story: Record<string, unknown>; branch_id?: string }>(`/settings/rules${projectId ? `?project_id=${encodeURIComponent(projectId)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}${branchId ? `&branch_id=${encodeURIComponent(branchId)}` : ''}` : ''}`),
  updateSettingsRules: (scope: 'global' | 'project' | 'story', rules: Record<string, unknown>, projectId?: string, storyId?: string, branchId?: string) => request<{ rules: Record<string, unknown>; saved: boolean; branch_id?: string }>(`/settings/rules/${scope}${projectId ? `?project_id=${encodeURIComponent(projectId)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}${branchId ? `&branch_id=${encodeURIComponent(branchId)}` : ''}` : ''}`, { method: 'PUT', body: JSON.stringify({ rules }) }),
  promptOptions: (layer: 'global' | 'project' | 'story', projectId?: string, storyId?: string, branchId?: string) => request<{ layer: string; options: Record<string, unknown>[]; branch_id?: string }>(`/settings/prompt-options?layer=${layer}${projectId ? `&project_id=${encodeURIComponent(projectId)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}${branchId ? `&branch_id=${encodeURIComponent(branchId)}` : ''}` : ''}`),
  updatePromptOptions: (layer: 'global' | 'project' | 'story', options: Record<string, unknown>[], projectId?: string, storyId?: string, branchId?: string) => request<{ options: Record<string, unknown>[]; saved: boolean; branch_id?: string }>(`/settings/prompt-options/${layer}${projectId ? `?project_id=${encodeURIComponent(projectId)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}${branchId ? `&branch_id=${encodeURIComponent(branchId)}` : ''}` : ''}`, { method: 'PUT', body: JSON.stringify({ options, ...(branchId ? { branch_id: branchId } : {}) }) }),
  autoConfiguration: (operation: string, projectId?: string, storyId = 'default') => request<{ state: Record<string, unknown>; revisions: unknown[] }>(`/settings/auto-configuration?operation=${encodeURIComponent(operation)}${projectId ? `&project_id=${encodeURIComponent(projectId)}&story_id=${encodeURIComponent(storyId)}` : ''}`),
  configureAutoConfiguration: (operation: string, payload: { goal?: string; source_chars?: number; locked_fields?: string[] }, projectId: string, storyId = 'default') => request<Record<string, unknown>>(`/settings/auto-configuration?project_id=${encodeURIComponent(projectId)}&story_id=${encodeURIComponent(storyId)}`, { method: 'POST', body: JSON.stringify({ operation, ...payload }) }),
  workspace: (projectId: string, storyId: string, branchId?: string) =>
    request<{ story: StoryItem; profile: Record<string, unknown>; outline: string; volumes: unknown[]; arcs: unknown[]; chapters: unknown[] }>(
      `/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/workspace${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`,
    ),
  structure: (projectId: string, storyId: string) =>
    request<{ volumes: unknown[]; arcs: unknown[]; chapters: unknown[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/structure`),
  contextPreview: (projectId: string, storyId: string, query = '', chapterNo?: number, budget = 24000, branchId?: string) =>
    request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/context/preview?query=${encodeURIComponent(query)}${chapterNo ? `&chapter_no=${chapterNo}` : ''}&budget=${budget}${branchId ? `&branch_id=${encodeURIComponent(branchId)}` : ''}`),
  rules: (projectId: string, storyId: string, branchId?: string) => request<{ project: Record<string, unknown>; story: Record<string, unknown>; branch_id?: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/rules${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`),
  updateRules: (projectId: string, storyId: string, rules: Record<string, unknown>, branchId?: string) => request<{ story: Record<string, unknown>; saved: boolean; branch_id?: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/rules${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`, { method: 'PUT', body: JSON.stringify({ rules, ...(branchId ? { branch_id: branchId } : {}) }) }),
  volume: (projectId: string, storyId: string, volumeNo: number) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/volumes/${volumeNo}`),
  updateVolume: (projectId: string, storyId: string, volumeNo: number, outline: string) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/volumes/${volumeNo}`, { method: 'PUT', body: JSON.stringify({ outline }) }),
  deleteVolume: (projectId: string, storyId: string, volumeNo: number) => request<{ deleted: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/volumes/${volumeNo}`, { method: 'DELETE' }),
  arc: (projectId: string, storyId: string, arcNo: number) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/arcs/${arcNo}`),
  arcChapterPlan: (projectId: string, storyId: string, arcNo: number) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/arcs/${arcNo}/chapter-plan`),
  updateArcChapterPlan: (projectId: string, storyId: string, arcNo: number, plan: Record<string, unknown>, reportMarkdown: string) => request<{ plan: Record<string, unknown>; saved: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/arcs/${arcNo}/chapter-plan`, { method: 'PUT', body: JSON.stringify({ plan, report_markdown: reportMarkdown }) }),
  updateArc: (projectId: string, storyId: string, arcNo: number, outline: string) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/arcs/${arcNo}`, { method: 'PUT', body: JSON.stringify({ outline }) }),
  deleteArc: (projectId: string, storyId: string, arcNo: number) => request<{ deleted: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/arcs/${arcNo}`, { method: 'DELETE' }),
  summary: (projectId: string, storyId = 'default') =>
    request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/summary?story_id=${encodeURIComponent(storyId)}`),
  content: (projectId: string, storyId = 'default', cursor: number | string = '', pageSize = 40) => {
    const cursorParam = cursor === '' ? '' : `&cursor=${encodeURIComponent(String(cursor))}`
    return request<{ items: any[]; next_cursor?: string; total?: number }>(`/projects/${encodeURIComponent(projectId)}/content?story_id=${encodeURIComponent(storyId)}${cursorParam}&page_size=${pageSize}`)
  },
  works: (projectId: string, storyId: string, cursor = '', pageSize = 40, branchId?: string) => request<{ items: any[]; next_cursor?: string; total?: number }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/works?page_size=${pageSize}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}${branchId ? `&branch_id=${encodeURIComponent(branchId)}` : ''}`),
  deleteChapterWork: (projectId: string, storyId: string, chapterNo: number, branchId?: string) => request<{ deleted: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/works/chapters/${chapterNo}${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`, { method: 'DELETE' }),
  removeFragmentWork: (projectId: string, storyId: string, fragmentId: string, branchId?: string) => request<{ removed: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/works/fragments/${encodeURIComponent(fragmentId)}${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`, { method: 'DELETE' }),
  deleteContent: (projectId: string, resource: Record<string, unknown>, storyId = 'default') => request<{ deleted: boolean }>(`/projects/${encodeURIComponent(projectId)}/content/delete?story_id=${encodeURIComponent(storyId)}`, { method: 'POST', body: JSON.stringify({ resource, confirm: true }) }),
  tasks: (projectId: string, status?: string) =>
    request<{ ingestion: unknown[]; web_research: unknown[] }>(`/projects/${encodeURIComponent(projectId)}/tasks${status ? `?status_filter=${encodeURIComponent(status)}` : ''}`),
  ingestionTask: (projectId: string, taskId: string) => request<{ task: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/ingestion/${encodeURIComponent(taskId)}`),
  controlIngestionTask: (projectId: string, taskId: string, action: 'pause' | 'resume' | 'cancel' | 'retry') => request<{ task: Record<string, unknown>; action: string }>(`/projects/${encodeURIComponent(projectId)}/ingestion/${encodeURIComponent(taskId)}/control`, { method: 'POST', body: JSON.stringify({ action }) }),
  sources: (projectId: string) => request<{ sources: unknown[] }>(`/projects/${encodeURIComponent(projectId)}/sources`),
  ingestionWorkbench: (projectId: string) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/ingestion/workbench`),
  addPastedIngestionText: (projectId: string, storyId: string, text: string, title = '粘贴资料', scope: 'story' | 'project' = 'project') =>
    request<{ attachment?: unknown; task?: Record<string, unknown>; accepted_count?: number; warnings?: string[]; scope?: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/ingestion/text`, { method: 'POST', body: JSON.stringify({ text, title, scope }) }),
  uploadIngestionBatch: (projectId: string, storyId: string, files: File[], scope: 'story' | 'project' = 'project', useOcr = false) => { const form = new FormData(); files.forEach((file) => form.append('files', file, file.name)); form.append('scope', scope); form.append('use_ocr', String(useOcr)); return request<{ accepted_count: number; attachments: any[]; warnings: string[]; scope: string; ocr_requested: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/ingestion/batch`, { method: 'POST', body: form, timeoutMs: MATERIAL_UPLOAD_TIMEOUT_MS }) },
  previewOcr: (projectId: string, storyId: string, file: File, languages = 'chi_sim+eng', dpi = 200) => { const form = new FormData(); form.append('file', file, file.name); form.append('languages', languages); form.append('dpi', String(dpi)); return request<{ filename: string; parser_name: string; warnings: string[]; metadata: Record<string, unknown>; sections: Array<{ title: string; page: number; confidence: number; char_count: number; text_preview: string }>; progress: Array<Record<string, unknown>> }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/ingestion/ocr-preview`, { method: 'POST', body: form, timeoutMs: MATERIAL_UPLOAD_TIMEOUT_MS }) },
  ingestionAttachments: (projectId: string, storyId?: string) => request<{ attachments: any[] }>(`/projects/${encodeURIComponent(projectId)}/ingestion/attachments${storyId ? `?story_id=${encodeURIComponent(storyId)}` : ''}`),
  retryAttachment: (projectId: string, attachmentId: string, confirmOverBudget = false) => request<{ attachment?: unknown; task?: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/ingestion/attachments/${encodeURIComponent(attachmentId)}/retry`, { method: 'POST', body: JSON.stringify({ confirm_over_budget: confirmOverBudget }) }),
  promoteKnowledge: async (projectId: string, knowledgeIds: string[], attachmentId?: string, storyId?: string, branchId?: string) => {
    const result = await request<{ success?: boolean; promoted_count: number; items: any[]; blocked?: boolean | unknown[]; blocked_ids?: unknown[]; reason?: string }>(`/projects/${encodeURIComponent(projectId)}/knowledge/promote${knowledgeScopeQuery(storyId, branchId)}`, { method: 'POST', body: JSON.stringify({ knowledge_ids: knowledgeIds, ...(attachmentId ? { attachment_id: attachmentId } : {}) }) })
    const blocked = result.blocked === true || (Array.isArray(result.blocked) && result.blocked.length > 0) || Boolean(result.blocked_ids?.length)
    if (result.success === false || blocked) throw new ApiClientError(result.reason || '所选知识暂不能共享到项目，请先处理待确认或冲突项。', 409, 'promotion_blocked')
    return result
  },
  searchKnowledge: (projectId: string, query: string, storyId?: string, cursor = '', pageSize = 40, recordType = '', branchId?: string) =>
    request<{ items: unknown[]; next_cursor?: string }>(`/projects/${encodeURIComponent(projectId)}/knowledge/search?query=${encodeURIComponent(query)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}${branchId ? `&branch_id=${encodeURIComponent(branchId)}` : ''}&page_size=${Math.max(1, Math.min(pageSize, 100))}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}${recordType ? `&record_type=${encodeURIComponent(recordType)}` : ''}`),
  knowledgeDetail: (projectId: string, recordType: string, recordId: string, storyId?: string, branchId?: string) =>
    request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}${knowledgeScopeQuery(storyId, branchId)}`),
  knowledgeRevisions: (projectId: string, recordType: string, recordId: string, storyId?: string, branchId?: string) => request<{ revisions: any[] }>(`/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}/revisions${knowledgeScopeQuery(storyId, branchId)}`),
  updateKnowledge: (projectId: string, recordType: string, recordId: string, patch: Record<string, unknown>, reason?: string, expectedRevisionId?: string, storyId?: string, branchId?: string) => request<{ record: Record<string, unknown>; saved: boolean; created_override?: boolean; origin_knowledge_id?: string }>(`/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}${knowledgeScopeQuery(storyId, branchId)}`, { method: 'PUT', body: JSON.stringify({ patch, reason, expected_revision_id: expectedRevisionId }) }),
  restoreKnowledgeRevision: (projectId: string, recordType: string, recordId: string, revisionId: string, storyId?: string, branchId?: string) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}/restore${knowledgeScopeQuery(storyId, branchId)}`, { method: 'POST', body: JSON.stringify({ revision_id: revisionId }) }),
  knowledgeGraph: (projectId: string, storyId?: string, branchId?: string) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/knowledge/graph${knowledgeScopeQuery(storyId, branchId)}`),
  knowledgeEntities: (projectId: string, entityType: 'character' | 'setting' | 'timeline', storyId?: string, branchId?: string) => request<{ entity_type: string; items: any[] }>(`/projects/${encodeURIComponent(projectId)}/knowledge/entities?entity_type=${entityType}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}${branchId ? `&branch_id=${encodeURIComponent(branchId)}` : ''}`),
  knowledgeEvidence: (projectId: string, recordType: string, recordId: string, storyId?: string, branchId?: string) => request<{ evidence: any[] }>(`/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}/evidence${knowledgeScopeQuery(storyId, branchId)}`),
  knowledgeSchema: (category: string) => request<{ category: string; fields: any[]; schema_version: number }>(`/knowledge/schema/${encodeURIComponent(category)}`),
  pendingKnowledge: (projectId: string, storyId?: string, branchId?: string) => request<{ items: any[] }>(`/projects/${encodeURIComponent(projectId)}/knowledge/pending${knowledgeScopeQuery(storyId, branchId)}`),
  resolvePendingEntity: (projectId: string, pendingId: string, targetEntityId: string, storyId?: string, branchId?: string) =>
    request<{ candidate: Record<string, unknown>; resolved: boolean }>(`/projects/${encodeURIComponent(projectId)}/knowledge/pending/${encodeURIComponent(pendingId)}/resolve-entity${knowledgeScopeQuery(storyId, branchId)}`, {
      method: 'POST',
      body: JSON.stringify({ target_entity_id: targetEntityId }),
    }),
  confirmPending: (projectId: string, pendingIds: string[], storyId?: string, branchId?: string) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/knowledge/pending/confirm${knowledgeScopeQuery(storyId, branchId)}`, { method: 'POST', body: JSON.stringify({ pending_ids: pendingIds }) }),
  discardPending: (projectId: string, pendingIds: string[], storyId?: string, branchId?: string) => request<{ removed_count: number }>(`/projects/${encodeURIComponent(projectId)}/knowledge/pending/discard${knowledgeScopeQuery(storyId, branchId)}`, { method: 'POST', body: JSON.stringify({ pending_ids: pendingIds }) }),
  outline: (projectId: string, storyId: string) =>
    request<{ content: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/outline`),
  updateOutline: (projectId: string, storyId: string, content: string) =>
    request<{ content: string; saved: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/outline`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),
  chapter: (projectId: string, storyId: string, chapterNo: number, branchId?: string) =>
    request<{ chapter: Record<string, unknown>; outline: string; content: string; review: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/chapters/${chapterNo}${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`),
  updateChapter: (projectId: string, storyId: string, chapterNo: number, content: string, kind: 'content' | 'outline' = 'content', branchId?: string) =>
    request<{ chapter_no: number; kind: string; content: string; saved: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/chapters/${chapterNo}${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`, { method: 'PUT', body: JSON.stringify({ content, kind }) }),
  chapterVersions: (projectId: string, storyId: string, chapterNo: number, branchId?: string) => request<{ versions: any[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/chapters/${chapterNo}/versions${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`),
  validateArcChapterPlan: (projectId: string, storyId: string, arcNo: number, plan: Record<string, unknown>) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/arcs/${arcNo}/chapter-plan/validate`, { method: 'POST', body: JSON.stringify({ plan }) }),
  sessions: (projectId: string, storyId: string, branchId?: string, includeArchived = false) => {
    const query = branchId || includeArchived ? `?${branchId ? `branch_id=${encodeURIComponent(branchId)}` : ''}${branchId && includeArchived ? '&' : ''}${includeArchived ? 'include_archived=true' : ''}` : ''
    return request<{ sessions: CreativeSession[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions${query}`)
  },
  archiveSession: (projectId: string, storyId: string, sessionId: string) =>
    request<{ session: CreativeSession; archived: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
  renameSession: (projectId: string, storyId: string, sessionId: string, title: string) =>
    request<{ session: CreativeSession }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  createSession: (projectId: string, storyId: string, payload: { session_goal: string; title?: string; branch_id?: string }) =>
    request<{ session: CreativeSession }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  session: (projectId: string, storyId: string, sessionId: string, branchId?: string) =>
    request<{ session: CreativeSession; turns: CreativeTurn[]; fragments: CreativeFragment[]; attachments?: unknown[] }>(
      `/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`,
    ),
  attachments: (projectId: string, storyId: string, sessionId: string, branchId?: string) =>
    request<{ attachments: unknown[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/attachments${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`),
  addPastedAttachment: (projectId: string, storyId: string, sessionId: string, text: string, title = '粘贴资料', scope: 'story' | 'project' = 'story', branchId?: string) =>
    request<{ attachment: unknown }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/attachments`, { method: 'POST', body: JSON.stringify({ text, title, scope, ...(branchId ? { branch_id: branchId } : {}) }) }),
  addFileAttachment: (projectId: string, storyId: string, sessionId: string, file: File, scope: 'story' | 'project' = 'story', branchId?: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('scope', scope)
    if (branchId) form.append('branch_id', branchId)
    return request<{ attachment: unknown; warnings?: string[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/attachments/file`, { method: 'POST', body: form, timeoutMs: MATERIAL_UPLOAD_TIMEOUT_MS })
  },
  actions: (projectId: string, storyId: string, sessionId: string, branchId?: string) => request<{ actions: CreativeAction[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/actions${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ''}`),
  planAction: (projectId: string, storyId: string, sessionId: string, requestText: string, branchId?: string) => request<{ action: CreativeAction }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/actions/plan`, { method: 'POST', body: JSON.stringify({ request: requestText, ...(branchId ? { branch_id: branchId } : {}) }) }),
  executeAction: (projectId: string, storyId: string, sessionId: string, actionId: string, confirmed: boolean, branchId?: string) => request<{ action: CreativeAction }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/execute`, { method: 'POST', body: JSON.stringify({ confirmed, ...(branchId ? { branch_id: branchId } : {}) }) }),
  cancelAction: (projectId: string, storyId: string, sessionId: string, actionId: string, branchId?: string) => request<{ action: CreativeAction }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/cancel`, { method: 'POST', body: JSON.stringify({ ...(branchId ? { branch_id: branchId } : {}) }) }),
  undoAction: (projectId: string, storyId: string, sessionId: string, actionId: string, branchId?: string) => request<{ action: CreativeAction }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/undo`, { method: 'POST', body: JSON.stringify({ ...(branchId ? { branch_id: branchId } : {}) }) }),
  acceptFragment: (projectId: string, storyId: string, sessionId: string, fragmentId: string, branchId?: string) =>
    request<{ fragment: CreativeFragment }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/fragments/accept`, {
      method: 'POST',
      body: JSON.stringify({ fragment_id: fragmentId, ...(branchId ? { branch_id: branchId } : {}) }),
    }),
  selectFragment: (projectId: string, storyId: string, sessionId: string, fragmentId: string, branchId?: string) =>
    request<{ fragment: CreativeFragment }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/fragments/select`, {
      method: 'POST',
      body: JSON.stringify({ fragment_id: fragmentId, ...(branchId ? { branch_id: branchId } : {}) }),
    }),
  selectFrontier: (projectId: string, storyId: string, sessionId: string, fragmentId: string, branchId?: string) =>
    request<{ session: CreativeSession }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/frontier`, {
      method: 'POST',
      body: JSON.stringify({ fragment_id: fragmentId, ...(branchId ? { branch_id: branchId } : {}) }),
    }),
  streamFragmentExtraction: async (
    projectId: string,
    storyId: string,
    sessionId: string,
    fragmentId: string,
    branchId: string | undefined,
    onEvent: (event: string, data: any) => void,
  ) => {
    await streamSse(
      `/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/fragments/${encodeURIComponent(fragmentId)}/extract/stream`,
      {
        method: 'POST',
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', 'X-Request-Id': requestId(), 'X-NovelForge-Client': 'vue', 'Idempotency-Key': requestId() },
        body: JSON.stringify(branchId ? { branch_id: branchId } : {}),
      },
      onEvent,
      '设定提炼',
    )
  },
  streamTurn: async (
    projectId: string,
    storyId: string,
    sessionId: string,
    payload: { user_message: string; action_type?: string; word_count?: string; branch_from_fragment_id?: string; enable_web_search?: boolean; branch_id?: string },
    onEvent: (event: string, data: any) => void,
  ) => {
    await streamSse(
      `/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/turns/stream`,
      {
        method: 'POST',
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', 'X-Request-Id': requestId(), 'X-NovelForge-Client': 'vue', 'Idempotency-Key': requestId() },
        body: JSON.stringify(payload),
      },
      onEvent,
      '流式请求',
    )
  },
  streamDiscussion: async (
    projectId: string,
    storyId: string,
    assetType: 'profile' | 'outline' | 'volume' | 'arc' | 'chapter',
    idea: string,
    onEvent: (event: string, data: any) => void,
    assetNo?: number,
    branchId?: string,
  ) => {
    const query = new URLSearchParams()
    if (assetNo) query.set('asset_no', String(assetNo))
    if (branchId) query.set('branch_id', branchId)
    await streamSse(
      `/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/discussions/${assetType}/stream${query.toString() ? `?${query}` : ''}`,
      {
        method: 'POST',
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', 'X-Request-Id': requestId(), 'X-NovelForge-Client': 'vue', 'Idempotency-Key': requestId() },
        body: JSON.stringify({ idea, ...(branchId ? { branch_id: branchId } : {}) }),
      },
      onEvent,
      '讨论请求',
    )
  },
}
