import type { CreativeSession } from '../types'

export function mostRecentActiveSession(sessions: CreativeSession[]): CreativeSession | undefined {
  // The API returns sessions newest first (updated_at DESC).
  return sessions.find((session) => session.status === 'active')
}

export function conversationRouteTarget(sessions: CreativeSession[]) {
  const recent = mostRecentActiveSession(sessions)
  return recent
    ? { name: 'conversational-session', params: { sessionId: recent.session_id } }
    : { name: 'conversational-home' }
}
