import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test.describe('双工作台入口', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [], frontend_modes: ['planned', 'conversational'] } } }))
  })

  test('模式选择器展示两套独立 UI，并在移动视口可用', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /你想怎样/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /进入规划工作台/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /进入对话工作台/ })).toBeVisible()
    await page.screenshot({ path: 'test-results/mode-picker-mobile.png', fullPage: true })
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    expect(overflow).toBe(false)
  })

  test('键盘可以访问两个工作台入口，首屏性能指标有界', async ({ page }) => {
    await page.goto('/')
    let focusedRole: string | null = null
    for (let index = 0; index < 12 && !focusedRole; index += 1) {
      await page.keyboard.press('Tab')
      focusedRole = await page.evaluate(() => document.activeElement?.getAttribute('href') || null)
    }
    expect(['/planned', '/conversational']).toContain(focusedRole)
    const timing = await page.evaluate(() => performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming)
    expect(timing.domContentLoadedEventEnd - timing.startTime).toBeLessThan(1500)
  })

  test('两套 Layout 路由互不串页，刷新后仍可回到入口', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('link', { name: /进入规划工作台/ }).click()
    await expect(page.getByText('规划模式', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByText('规划模式', { exact: true })).toBeVisible()
    await page.goto('/')
    await page.getByRole('link', { name: /进入对话工作台/ }).click()
    await expect(page.getByText('自由对话', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByText('自由对话', { exact: true })).toBeVisible()
  })

  test('已有故事从入口切换模式时会先持久化模式再进入对应工作台', async ({ page }) => {
    let creationMode: 'planned' | 'conversational' = 'planned'
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-switch', name: '切换项目', title: '切换项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-switch/stories', async (route) => {
      await route.fulfill({ json: { data: { stories: [{ story_id: 's-switch', name: '切换故事', creation_mode: creationMode }] } } })
    })
    await page.route('**/api/v1/projects/p-switch/stories/s-switch/mode', async (route) => {
      const payload = route.request().postDataJSON() as { creation_mode: 'planned' | 'conversational' }
      creationMode = payload.creation_mode
      await route.fulfill({ json: { data: { story: { story_id: 's-switch', name: '切换故事', creation_mode: creationMode } } } })
    })
    await page.goto('/')
    await page.getByRole('link', { name: /进入对话工作台/ }).click()
    await expect(page.getByText('自由对话', { exact: true })).toBeVisible()
    await page.goto('/')
    await page.getByRole('link', { name: /进入规划工作台/ }).click()
    await expect(page.getByText('规划模式', { exact: true })).toBeVisible()
    expect(creationMode).toBe('planned')
  })

  test('模式选择页通过核心可访问性扫描', async ({ page }) => {
    await page.goto('/')
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
    expect(results.violations).toEqual([])
  })

  test('两套 Layout 通过核心可访问性扫描', async ({ page }) => {
    for (const path of ['/planned', '/conversational']) {
      await page.goto(path)
      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
      expect(results.violations, `${path} accessibility violations`).toEqual([])
    }
  })

  test('桌面关键视口保持双卡片布局且支持 reduced motion', async ({ browser }) => {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 800 }, { width: 1024, height: 768 }, { width: 768, height: 1024 }]) {
      const page = await browser.newPage({ viewport, reducedMotion: 'reduce' })
      await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [], frontend_modes: ['planned', 'conversational'] } } }))
      await page.goto('/')
      await expect(page.getByRole('link', { name: /进入规划工作台/ })).toBeVisible()
      await expect(page.getByRole('link', { name: /进入对话工作台/ })).toBeVisible()
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
      expect(overflow).toBe(false)
      await page.screenshot({ path: `test-results/mode-picker-${viewport.width}x${viewport.height}.png`, fullPage: true })
      await page.close()
    }
  })

  test('中文组合输入期间不会误触发发送，并可承载长草稿', async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-ime', name: 'IME 项目', title: 'IME 项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-ime/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-ime', name: 'IME 故事', creation_mode: 'conversational' }] } } }))
    let sessionRequests = 0
    await page.route('**/api/v1/projects/p-ime/stories/s-ime/sessions', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ json: { data: { sessions: [] } } })
        return
      }
      sessionRequests += 1
      await route.fulfill({ json: { data: { session: { session_id: 'sess-ime', title: 'IME 会话', status: 'active' } } } })
    })
    await page.route('**/api/v1/projects/p-ime/stories/s-ime/sessions/sess-ime', async (route) => route.fulfill({ json: { data: { session: { session_id: 'sess-ime', title: 'IME 会话', status: 'active' }, turns: [], fragments: [], attachments: [] } } }))
    await page.route('**/api/v1/projects/p-ime/stories/s-ime/sessions/sess-ime/actions', async (route) => route.fulfill({ json: { data: { actions: [] } } }))
    await page.goto('/')
    await page.getByRole('link', { name: /进入对话工作台/ }).click()
    const composer = page.locator('textarea').first()
    await expect(composer).toBeVisible()
    await composer.dispatchEvent('compositionstart')
    await composer.fill('这是一段组合输入中的中文草稿')
    await composer.press('Control+Enter')
    expect(sessionRequests).toBe(0)
    await composer.dispatchEvent('compositionend')
    await composer.press('Control+Enter')
    await expect.poll(() => sessionRequests).toBe(1)
  })

  test('长草稿在移动视口不产生横向溢出', async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-long', name: '长文项目', title: '长文项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-long/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-long', name: '长文故事', creation_mode: 'conversational' }] } } }))
    await page.route('**/api/v1/projects/p-long/stories/s-long/sessions', async (route) => route.fulfill({ json: { data: { sessions: [] } } }))
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')
    await page.getByRole('link', { name: /进入对话工作台/ }).click()
    const composer = page.locator('textarea').first()
    const longDraft = '长文本段落。'.repeat(8_000)
    await composer.fill(longDraft)
    await expect(composer).toHaveValue(longDraft)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    expect(overflow).toBe(false)
  })
})
