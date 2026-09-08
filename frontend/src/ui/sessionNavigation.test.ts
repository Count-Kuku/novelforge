import { describe, expect, it } from 'vitest'
import type { CreativeSession } from '../types'
import { conversationRouteTarget, mostRecentActiveSession } from './sessionNavigation'

function session(sessionId: string, status = 'active'): CreativeSession {
  return {
    session_id: sessionId,
    story_id: 'story-1',
    title: sessionId,
    status,
    session_goal: '',
    auto_extract_mode: 'manual',
    updated_at: '2026-09-08T00:00:00Z',
  }
}

describe('conversation navigation', () => {
  it('returns the first active session because the API orders newest first', () => {
    const sessions = [session('newest'), session('archived', 'archived'), session('oldest')]
    expect(mostRecentActiveSession(sessions)?.session_id).toBe('newest')
    expect(conversationRouteTarget(sessions)).toEqual({
      name: 'conversational-session',
      params: { sessionId: 'newest' },
    })
  })

  it('opens the creation page when there is no active session', () => {
    expect(conversationRouteTarget([session('archived', 'archived')])).toEqual({ name: 'conversational-home' })
  })
})
