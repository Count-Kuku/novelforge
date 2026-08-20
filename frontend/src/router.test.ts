import { describe, expect, it } from 'vitest'
import { router } from './router'

describe('双工作台路由', () => {
  it('同时暴露规划与对话两套入口', () => {
    const names = router.getRoutes().map((route) => String(route.name || ''))
    expect(names).toEqual(expect.arrayContaining([
      'planned-direction',
      'planned-outline',
      'planned-chapters',
      'conversational-home',
      'conversational-session',
      'planned-settings',
      'conversational-settings',
      'planned-volume',
      'planned-arc',
      'planned-knowledge-graph',
      'planned-research',
      'planned-rules',
      'conversational-knowledge-graph',
      'conversational-research',
      'conversational-rules',
    ]))
  })

  it('两套入口使用不同的布局组件', () => {
    const planned = router.options.routes.find((route) => route.path === '/planned')
    const conversational = router.options.routes.find((route) => route.path === '/conversational')
    expect(planned?.children?.map((child) => child.name)).toContain('planned-outline')
    expect(conversational?.children?.map((child) => child.name)).toContain('conversational-session')
    expect(planned?.component).not.toBe(conversational?.component)
  })
})
