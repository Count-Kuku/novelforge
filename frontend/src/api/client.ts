import type {
  BootstrapData,
  CreationMode,
  CreativeSession,
  CreativeFragment,
  CreativeAction,
  CreativeTurn,
  ProjectItem,
  StoryItem,
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || 'GET').toUpperCase()
  const controller = new AbortController()
  const timeout = globalThis.setTimeout(() => controller.abort(), 20_000)
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: init.signal || controller.signal,
      headers: {
        Accept: 'application/json',
        'X-Request-Id': requestId(),
        ...(init.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...(method !== 'GET' && method !== 'HEAD' ? { 'X-NovelForge-Client': 'vue', 'Idempotency-Key': requestId() } : {}),
        ...(init.headers || {}),
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
  renameStory: (projectId: string, storyId: string, name: string, description?: string) => request<{ story: StoryItem }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}`, { method: 'PATCH', body: JSON.stringify({ name, description }) }),
  copyStory: (projectId: string, storyId: string, payload: { name: string; include_discussions?: boolean; include_summaries?: boolean; include_chapters?: boolean }) =>
    request<{ story: StoryItem }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/copy`, { method: 'POST', body: JSON.stringify(payload) }),
  archiveStory: (projectId: string, storyId: string) => request<{ archived: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/archive`, { method: 'POST' }),
  setStoryMode: (projectId: string, storyId: string, creationMode: CreationMode) =>
    request<{ story: StoryItem }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/mode`, {
      method: 'PATCH',
      body: JSON.stringify({ creation_mode: creationMode }),
    }),
  profile: (projectId: string, storyId: string) =>
    request<{ profile: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/profile`),
  updateProfile: (projectId: string, storyId: string, profile: Record<string, unknown>) =>
    request<{ profile: Record<string, unknown>; saved: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/profile`, {
      method: 'PUT',
      body: JSON.stringify({ profile }),
    }),
  discussionArtifact: (projectId: string, storyId: string, assetType: 'profile' | 'outline' | 'volume' | 'arc' | 'chapter', assetNo?: number) =>
    request<{ asset_type: string; artifact: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/discussions/${assetType}${assetNo ? `?asset_no=${assetNo}` : ''}`),
  approveDiscussion: (projectId: string, storyId: string, assetType: 'profile' | 'outline' | 'volume' | 'arc' | 'chapter', step: Record<string, unknown>, assetNo?: number) =>
    request<{ asset_type: string; result: unknown }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/discussions/${assetType}/approve${assetNo ? `?asset_no=${assetNo}` : ''}`, { method: 'POST', body: JSON.stringify({ step }) }),
  capabilities: () => request<{ capabilities: Record<string, { available: boolean; status: string; message: string; provider?: string }> }>('/capabilities'),
  developerSettings: () => request<{ enabled: boolean; projections: string[] }>('/settings/developer'),
  operationEvents: (operationId: string, after = 0) => request<{ operation_id: string; events: OperationEvent[] }>(`/operations/${encodeURIComponent(operationId)}/events?after=${Math.max(0, after)}`),
  cancelOperation: (operationId: string) => request<{ operation_id: string; status: string }>(`/operations/${encodeURIComponent(operationId)}/cancel`, { method: 'POST', body: '{}' }),
  usage: (projectId?: string, storyId?: string) => request<{ today: Record<string, unknown>; month: Record<string, unknown>; daily: unknown[]; recent: unknown[] }>(`/usage${projectId ? `?project_id=${encodeURIComponent(projectId)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}` : ''}`),
  usageBreakdown: (dimension: 'project' | 'story' | 'model' | 'operation' | 'agent', projectId?: string, storyId?: string) => request<{ dimension: string; rows: Record<string, unknown>[] }>(`/usage/breakdown?dimension=${encodeURIComponent(dimension)}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ''}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}`),
  modelProfiles: () => request<{ active_profile_id: string; profiles: Record<string, unknown>[] }>('/settings/models'),
  updateModelProfile: (profile: Record<string, unknown>) => request<{ profile: Record<string, unknown>; saved: boolean }>('/settings/models', { method: 'PUT', body: JSON.stringify(profile) }),
  activateModelProfile: (profileId: string) => request<{ profile: Record<string, unknown>; active_profile_id: string }>('/settings/models/active', { method: 'POST', body: JSON.stringify({ profile_id: profileId }) }),
  settingsRules: (projectId?: string, storyId?: string) => request<{ global: Record<string, unknown>; project: Record<string, unknown>; story: Record<string, unknown> }>(`/settings/rules${projectId ? `?project_id=${encodeURIComponent(projectId)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}` : ''}`),
  updateSettingsRules: (scope: 'global' | 'project' | 'story', rules: Record<string, unknown>, projectId?: string, storyId?: string) => request<{ rules: Record<string, unknown>; saved: boolean }>(`/settings/rules/${scope}${projectId ? `?project_id=${encodeURIComponent(projectId)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}` : ''}`, { method: 'PUT', body: JSON.stringify({ rules }) }),
  promptOptions: (layer: 'global' | 'project' | 'story', projectId?: string, storyId?: string) => request<{ layer: string; options: Record<string, unknown>[] }>(`/settings/prompt-options?layer=${layer}${projectId ? `&project_id=${encodeURIComponent(projectId)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}` : ''}`),
  updatePromptOptions: (layer: 'global' | 'project' | 'story', options: Record<string, unknown>[], projectId?: string, storyId?: string) => request<{ options: Record<string, unknown>[]; saved: boolean }>(`/settings/prompt-options/${layer}${projectId ? `?project_id=${encodeURIComponent(projectId)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}` : ''}`, { method: 'PUT', body: JSON.stringify({ options }) }),
  autoConfiguration: (operation: string, projectId?: string, storyId = 'default') => request<{ state: Record<string, unknown>; revisions: unknown[] }>(`/settings/auto-configuration?operation=${encodeURIComponent(operation)}${projectId ? `&project_id=${encodeURIComponent(projectId)}&story_id=${encodeURIComponent(storyId)}` : ''}`),
  configureAutoConfiguration: (operation: string, payload: { goal?: string; source_chars?: number; locked_fields?: string[] }, projectId: string, storyId = 'default') => request<Record<string, unknown>>(`/settings/auto-configuration?project_id=${encodeURIComponent(projectId)}&story_id=${encodeURIComponent(storyId)}`, { method: 'POST', body: JSON.stringify({ operation, ...payload }) }),
  workspace: (projectId: string, storyId: string) =>
    request<{ story: StoryItem; profile: Record<string, unknown>; outline: string; volumes: unknown[]; arcs: unknown[]; chapters: unknown[] }>(
      `/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/workspace`,
    ),
  structure: (projectId: string, storyId: string) =>
    request<{ volumes: unknown[]; arcs: unknown[]; chapters: unknown[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/structure`),
  contextPreview: (projectId: string, storyId: string, query = '', chapterNo?: number, budget = 24000) =>
    request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/context/preview?query=${encodeURIComponent(query)}${chapterNo ? `&chapter_no=${chapterNo}` : ''}&budget=${budget}`),
  rules: (projectId: string, storyId: string) => request<{ project: Record<string, unknown>; story: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/rules`),
  updateRules: (projectId: string, storyId: string, rules: Record<string, unknown>) => request<{ story: Record<string, unknown>; saved: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/rules`, { method: 'PUT', body: JSON.stringify({ rules }) }),
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
  content: (projectId: string, storyId = 'default', cursor = '', pageSize = 40) => request<{ items: any[]; next_cursor?: string; total?: number }>(`/projects/${encodeURIComponent(projectId)}/content?story_id=${encodeURIComponent(storyId)}&cursor=${encodeURIComponent(cursor)}&page_size=${pageSize}`),
  deleteContent: (projectId: string, resource: Record<string, unknown>, storyId = 'default') => request<{ deleted: boolean }>(`/projects/${encodeURIComponent(projectId)}/content/delete?story_id=${encodeURIComponent(storyId)}`, { method: 'POST', body: JSON.stringify({ resource, confirm: true }) }),
  tasks: (projectId: string, status?: string) =>
    request<{ ingestion: unknown[]; web_research: unknown[] }>(`/projects/${encodeURIComponent(projectId)}/tasks${status ? `?status_filter=${encodeURIComponent(status)}` : ''}`),
  ingestionTask: (projectId: string, taskId: string) => request<{ task: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/ingestion/${encodeURIComponent(taskId)}`),
  controlIngestionTask: (projectId: string, taskId: string, action: 'pause' | 'resume' | 'cancel' | 'retry') => request<{ task: Record<string, unknown>; action: string }>(`/projects/${encodeURIComponent(projectId)}/ingestion/${encodeURIComponent(taskId)}/control`, { method: 'POST', body: JSON.stringify({ action }) }),
  sources: (projectId: string) => request<{ sources: unknown[] }>(`/projects/${encodeURIComponent(projectId)}/sources`),
  createResearchTask: (projectId: string, payload: Record<string, unknown>) => request<{ task: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/research`, { method: 'POST', body: JSON.stringify(payload) }),
  researchTask: (projectId: string, taskId: string) => request<{ task: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/research/${encodeURIComponent(taskId)}`),
  controlResearchTask: (projectId: string, taskId: string, action: 'pause' | 'resume' | 'cancel' | 'retry') => request<{ task: Record<string, unknown>; action: string }>(`/projects/${encodeURIComponent(projectId)}/research/${encodeURIComponent(taskId)}/control`, { method: 'POST', body: JSON.stringify({ action }) }),
  reviewResearchClaims: (projectId: string, taskId: string, claimIds: string[]) => request<{ result: Record<string, unknown>; task: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/research/${encodeURIComponent(taskId)}/claims/review`, { method: 'POST', body: JSON.stringify({ claim_ids: claimIds }) }),
  activateResearchSources: (projectId: string, taskId: string) => request<{ task: Record<string, unknown>; result: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/research/${encodeURIComponent(taskId)}/sources/activate`, { method: 'POST', body: '{}' }),
  quarantineResearchSources: (projectId: string, taskId: string) => request<{ task: Record<string, unknown>; result: Record<string, unknown> }>(`/projects/${encodeURIComponent(projectId)}/research/${encodeURIComponent(taskId)}/sources/quarantine`, { method: 'POST', body: '{}' }),
  ingestionWorkbench: (projectId: string) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/ingestion/workbench`),
  uploadIngestionBatch: (projectId: string, storyId: string, files: File[], scope: 'story' | 'project' = 'project', useOcr = false) => { const form = new FormData(); files.forEach((file) => form.append('files', file, file.name)); form.append('scope', scope); form.append('use_ocr', String(useOcr)); return request<{ accepted_count: number; attachments: any[]; warnings: string[]; scope: string; ocr_requested: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/ingestion/batch`, { method: 'POST', body: form }) },
  previewOcr: (projectId: string, storyId: string, file: File, languages = 'chi_sim+eng', dpi = 200) => { const form = new FormData(); form.append('file', file, file.name); form.append('languages', languages); form.append('dpi', String(dpi)); return request<{ filename: string; parser_name: string; warnings: string[]; metadata: Record<string, unknown>; sections: Array<{ title: string; page: number; confidence: number; char_count: number; text_preview: string }>; progress: Array<Record<string, unknown>> }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/ingestion/ocr-preview`, { method: 'POST', body: form }) },
  searchKnowledge: (projectId: string, query: string, storyId?: string, cursor = '', pageSize = 40, recordType = '') =>
    request<{ items: unknown[]; next_cursor?: string }>(`/projects/${encodeURIComponent(projectId)}/knowledge/search?query=${encodeURIComponent(query)}${storyId ? `&story_id=${encodeURIComponent(storyId)}` : ''}&page_size=${Math.max(1, Math.min(pageSize, 100))}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}${recordType ? `&record_type=${encodeURIComponent(recordType)}` : ''}`),
  knowledgeDetail: (projectId: string, recordType: string, recordId: string) =>
    request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}`),
  knowledgeRevisions: (projectId: string, recordType: string, recordId: string) => request<{ revisions: any[] }>(`/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}/revisions`),
  updateKnowledge: (projectId: string, recordType: string, recordId: string, patch: Record<string, unknown>, reason?: string, expectedRevisionId?: string) => request<{ record: Record<string, unknown>; saved: boolean }>(`/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}`, { method: 'PUT', body: JSON.stringify({ patch, reason, expected_revision_id: expectedRevisionId }) }),
  restoreKnowledgeRevision: (projectId: string, recordType: string, recordId: string, revisionId: string) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}/restore`, { method: 'POST', body: JSON.stringify({ revision_id: revisionId }) }),
  knowledgeGraph: (projectId: string, storyId?: string) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/knowledge/graph${storyId ? `?story_id=${encodeURIComponent(storyId)}` : ''}`),
  knowledgeEntities: (projectId: string, entityType: 'character' | 'setting' | 'timeline') => request<{ entity_type: string; items: any[] }>(`/projects/${encodeURIComponent(projectId)}/knowledge/entities?entity_type=${entityType}`),
  knowledgeEvidence: (projectId: string, recordType: string, recordId: string) => request<{ evidence: any[] }>(`/projects/${encodeURIComponent(projectId)}/knowledge/${encodeURIComponent(recordType)}/${encodeURIComponent(recordId)}/evidence`),
  knowledgeSchema: (category: string) => request<{ category: string; fields: any[]; schema_version: number }>(`/knowledge/schema/${encodeURIComponent(category)}`),
  pendingKnowledge: (projectId: string) => request<{ items: any[] }>(`/projects/${encodeURIComponent(projectId)}/knowledge/pending`),
  confirmPending: (projectId: string, pendingIds: string[]) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/knowledge/pending/confirm`, { method: 'POST', body: JSON.stringify({ pending_ids: pendingIds }) }),
  discardPending: (projectId: string, pendingIds: string[]) => request<{ removed_count: number }>(`/projects/${encodeURIComponent(projectId)}/knowledge/pending/discard`, { method: 'POST', body: JSON.stringify({ pending_ids: pendingIds }) }),
  outline: (projectId: string, storyId: string) =>
    request<{ content: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/outline`),
  updateOutline: (projectId: string, storyId: string, content: string) =>
    request<{ content: string; saved: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/outline`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),
  chapter: (projectId: string, storyId: string, chapterNo: number) =>
    request<{ chapter: Record<string, unknown>; outline: string; content: string; review: string }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/chapters/${chapterNo}`),
  updateChapter: (projectId: string, storyId: string, chapterNo: number, content: string, kind: 'content' | 'outline' = 'content') =>
    request<{ chapter_no: number; kind: string; content: string; saved: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/chapters/${chapterNo}`, { method: 'PUT', body: JSON.stringify({ content, kind }) }),
  chapterVersions: (projectId: string, storyId: string, chapterNo: number) => request<{ versions: any[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/chapters/${chapterNo}/versions`),
  validateArcChapterPlan: (projectId: string, storyId: string, arcNo: number, plan: Record<string, unknown>) => request<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/arcs/${arcNo}/chapter-plan/validate`, { method: 'POST', body: JSON.stringify({ plan }) }),
  sessions: (projectId: string, storyId: string) =>
    request<{ sessions: CreativeSession[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions`),
  archiveSession: (projectId: string, storyId: string, sessionId: string) =>
    request<{ session: CreativeSession; archived: boolean }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
  renameSession: (projectId: string, storyId: string, sessionId: string, title: string) =>
    request<{ session: CreativeSession }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  createSession: (projectId: string, storyId: string, payload: { session_goal: string; title?: string }) =>
    request<{ session: CreativeSession }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  session: (projectId: string, storyId: string, sessionId: string) =>
    request<{ session: CreativeSession; turns: CreativeTurn[]; fragments: CreativeFragment[]; attachments?: unknown[] }>(
      `/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}`,
    ),
  attachments: (projectId: string, storyId: string, sessionId: string) =>
    request<{ attachments: unknown[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/attachments`),
  addPastedAttachment: (projectId: string, storyId: string, sessionId: string, text: string, title = '粘贴资料', scope: string = 'session') =>
    request<{ attachment: unknown }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/attachments`, { method: 'POST', body: JSON.stringify({ text, title, scope }) }),
  addUrlAttachment: (projectId: string, storyId: string, sessionId: string, url: string, scope: string = 'session') =>
    request<{ attachment: unknown }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/attachments/url`, { method: 'POST', body: JSON.stringify({ url, scope }) }),
  addFileAttachment: (projectId: string, storyId: string, sessionId: string, file: File, scope: string = 'session') => {
    const form = new FormData()
    form.append('file', file)
    form.append('scope', scope)
    return request<{ attachment: unknown; warnings?: string[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/attachments/file`, { method: 'POST', body: form })
  },
  actions: (projectId: string, storyId: string, sessionId: string) => request<{ actions: CreativeAction[] }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/actions`),
  planAction: (projectId: string, storyId: string, sessionId: string, requestText: string) => request<{ action: CreativeAction }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/actions/plan`, { method: 'POST', body: JSON.stringify({ request: requestText }) }),
  executeAction: (projectId: string, storyId: string, sessionId: string, actionId: string, confirmed: boolean) => request<{ action: CreativeAction }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/execute`, { method: 'POST', body: JSON.stringify({ confirmed }) }),
  cancelAction: (projectId: string, storyId: string, sessionId: string, actionId: string) => request<{ action: CreativeAction }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/cancel`, { method: 'POST', body: '{}' }),
  undoAction: (projectId: string, storyId: string, sessionId: string, actionId: string) => request<{ action: CreativeAction }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/undo`, { method: 'POST', body: '{}' }),
  acceptFragment: (projectId: string, storyId: string, sessionId: string, fragmentId: string) =>
    request<{ fragment: CreativeFragment }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/fragments/accept`, {
      method: 'POST',
      body: JSON.stringify({ fragment_id: fragmentId }),
    }),
  selectFragment: (projectId: string, storyId: string, sessionId: string, fragmentId: string) =>
    request<{ fragment: CreativeFragment }>(`/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/sessions/${encodeURIComponent(sessionId)}/fragments/select`, {
      method: 'POST',
      body: JSON.stringify({ fragment_id: fragmentId }),
    }),
  streamTurn: async (
    projectId: string,
    storyId: string,
    sessionId: string,
    payload: { user_message: string; action_type?: string; word_count?: string; branch_from_fragment_id?: string },
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
  ) => {
    await streamSse(
      `/projects/${encodeURIComponent(projectId)}/stories/${encodeURIComponent(storyId)}/discussions/${assetType}/stream${assetNo ? `?asset_no=${assetNo}` : ''}`,
      {
        method: 'POST',
        headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', 'X-Request-Id': requestId(), 'X-NovelForge-Client': 'vue', 'Idempotency-Key': requestId() },
        body: JSON.stringify({ idea }),
      },
      onEvent,
      '讨论请求',
    )
  },
}
