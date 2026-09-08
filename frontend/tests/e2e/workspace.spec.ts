import { test, expect, type Locator, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

async function expectReadable(locator: Locator) {
  const ratio = await locator.evaluate((element) => {
    const parse = (value: string) => {
      const match = value.match(/rgba?\(([^)]+)\)/)
      const parts = match?.[1].split(/[, ]+/).filter(Boolean).map(Number) || []
      return { r: parts[0] || 0, g: parts[1] || 0, b: parts[2] || 0, a: parts.length > 3 ? parts[3] : 1 }
    }
    const over = (front: ReturnType<typeof parse>, back: ReturnType<typeof parse>) => {
      const alpha = front.a + back.a * (1 - front.a)
      return { r: (front.r * front.a + back.r * back.a * (1 - front.a)) / alpha, g: (front.g * front.a + back.g * back.a * (1 - front.a)) / alpha, b: (front.b * front.a + back.b * back.a * (1 - front.a)) / alpha, a: alpha }
    }
    const luminance = (color: ReturnType<typeof parse>) => {
      const channel = (value: number) => { const normalized = value / 255; return normalized <= .04045 ? normalized / 12.92 : ((normalized + .055) / 1.055) ** 2.4 }
      return .2126 * channel(color.r) + .7152 * channel(color.g) + .0722 * channel(color.b)
    }
    const chain: Element[] = []
    for (let current: Element | null = element; current; current = current.parentElement) chain.push(current)
    let background = { r: 244, g: 240, b: 232, a: 1 }
    for (const current of chain.reverse()) background = over(parse(getComputedStyle(current).backgroundColor), background)
    const foreground = over(parse(getComputedStyle(element).color), background)
    const values = [luminance(foreground), luminance(background)]
    return (Math.max(...values) + .05) / (Math.min(...values) + .05)
  })
  expect(ratio).toBeGreaterThanOrEqual(4.5)
}

async function expectNoContrastViolations(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withRules(['color-contrast']).analyze()
  expect(results.violations, `${label} color contrast violations`).toEqual([])
}

test.describe('双工作台入口', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [], frontend_modes: ['planned', 'conversational'] } } }))
  })

  test('模式选择器展示两套独立 UI，并在移动视口可用', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /选择本次要进入的工作台/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /选择规划模式/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /选择对话模式/ })).toBeVisible()
    await page.getByRole('link', { name: /选择对话模式/ }).click()
    await expect(page.getByLabel('项目名称')).toBeFocused()
    await expect(page).toHaveURL('/')
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
    let creationMode: 'planned' | 'conversational' = 'planned'
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-layout', name: '布局项目', title: '布局项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-layout/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-layout', name: '布局故事', creation_mode: creationMode }] } } }))
    await page.route('**/api/v1/projects/p-layout/stories/s-layout/structure', async (route) => route.fulfill({ json: { data: { volumes: [], arcs: [], chapters: [] } } }))
    await page.route('**/api/v1/projects/p-layout/stories/s-layout/profile', async (route) => route.fulfill({ json: { data: { profile: {} } } }))
    await page.route('**/api/v1/projects/p-layout/stories/s-layout/sessions', async (route) => route.fulfill({ json: { data: { sessions: [] } } }))
    await page.route('**/api/v1/projects/p-layout/stories/s-layout/mode', async (route) => {
      creationMode = route.request().postDataJSON().creation_mode
      await route.fulfill({ json: { data: { story: { story_id: 's-layout', name: '布局故事', creation_mode: creationMode } } } })
    })
    await page.goto('/')
    await page.getByRole('link', { name: /进入规划工作台/ }).click()
    await expect(page.getByText('规划模式', { exact: true })).toBeVisible()
    await page.screenshot({ path: 'test-results/planned-layout.png', fullPage: true })
    await page.reload()
    await expect(page.getByText('规划模式', { exact: true })).toBeVisible()
    await page.goto('/')
    await page.getByRole('link', { name: /进入对话工作台/ }).click()
    await expect(page.getByText('自由对话', { exact: true })).toBeVisible()
    await page.screenshot({ path: 'test-results/conversational-layout.png', fullPage: true })
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

  test('对话工作台四入口固定在视口内，长内容页面不会推走主导航', async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-sidebar', name: '侧栏项目', title: '侧栏项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-sidebar/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-sidebar', name: '侧栏故事', creation_mode: 'conversational' }] } } }))
    await page.route('**/api/v1/projects/p-sidebar/stories/s-sidebar/sessions', async (route) => route.fulfill({ json: { data: { sessions: [] } } }))
    await page.setViewportSize({ width: 1024, height: 650 })
    await page.goto('/conversational')

    const sidebar = page.locator('.chat-sidebar')
    const footer = page.locator('.chat-sidebar-footer')
    await expect(sidebar).toBeVisible()
    await expect(footer.getByRole('link')).toHaveCount(4)
    await expect(footer.getByRole('link', { name: /对话/ })).toBeVisible()
    await expect(footer.getByRole('link', { name: /作品/ })).toBeVisible()
    await expect(footer.getByRole('link', { name: /资料库/ })).toBeVisible()
    await expect(footer.getByRole('link', { name: /设置/ })).toBeVisible()
    await expect(page.getByLabel('选择故事').locator('option').first()).toHaveCSS('color', 'rgb(255, 244, 234)')
    await expect(page.getByLabel('选择故事').locator('option').first()).toHaveCSS('background-color', 'rgb(106, 73, 60)')
    await expect(page.getByLabel('选择项目').locator('option').first()).toHaveCSS('color', 'rgb(255, 244, 234)')
    await expectReadable(page.getByText('⌘ / Ctrl + Enter 创建会话'))
    await expectReadable(page.getByText('写作片段和采用状态可追溯'))
    await expectNoContrastViolations(page, '对话首页')
    const initial = await page.evaluate(() => {
      const sidebarRect = document.querySelector('.chat-sidebar')!.getBoundingClientRect()
      const footerRect = document.querySelector('.chat-sidebar-footer')!.getBoundingClientRect()
      return { sidebarTop: sidebarRect.top, sidebarHeight: sidebarRect.height, footerBottom: footerRect.bottom, viewportHeight: window.innerHeight, documentHeight: document.documentElement.scrollHeight }
    })
    expect(initial.documentHeight).toBeGreaterThan(initial.viewportHeight)
    expect(initial.sidebarTop).toBeGreaterThanOrEqual(0)
    expect(initial.sidebarHeight).toBe(initial.viewportHeight)
    expect(initial.footerBottom).toBeLessThanOrEqual(initial.viewportHeight)

    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
    await expect(sidebar).toBeInViewport()
    await expect(footer).toBeInViewport()
    const scrolledTop = await sidebar.evaluate((element) => element.getBoundingClientRect().top)
    expect(Math.abs(scrolledTop)).toBeLessThan(1)
  })

  test('四入口中的对话、作品、资料库和设置承担各自内容', async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-four', name: '四入口项目', title: '四入口项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-four/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-four', name: '四入口故事', creation_mode: 'conversational' }] } } }))
    await page.route('**/api/v1/projects/p-four/stories/s-four/sessions', async (route) => route.fulfill({ json: { data: { sessions: [] } } }))
    await page.route('**/api/v1/projects/p-four/stories/s-four/works*', async (route) => route.fulfill({ json: { data: { total: 1, next_cursor: '', items: [{ id: 'fragment:one', kind: 'conversation_fragment', title: '雨夜开场', subtitle: '已采用片段', preview: '雨落在旧车站的玻璃顶上。', word_count: 13, updated_at: '2026-08-21T20:00:00+08:00', session_id: 'session-one', fragment_id: 'one' }] } } }))
    await page.route('**/api/v1/capabilities', async (route) => route.fulfill({ json: { data: { capabilities: {} } } }))
    await page.route('**/api/v1/settings/models', async (route) => route.fulfill({ json: { data: { active_profile_id: 'default', profiles: [{ id: 'default', name: '默认配置', provider_type: 'auto', base_url: '', model_name: '', embedding_mode: 'disabled', embedding_model_name: '' }] } } }))
    await page.route(/\/api\/v1\/usage\?.*$/, async (route) => route.fulfill({ json: { data: { today: { request_count: 0, total_tokens: 0, cost_usd: 0 }, month: { request_count: 0, cost_usd: 0, cost_complete: false }, daily: [], recent: [] } } }))
    await page.route(/\/api\/v1\/usage\/breakdown\?.*$/, async (route) => route.fulfill({ json: { data: { dimension: 'operation', rows: [] } } }))
    await page.goto('/conversational')

    await page.getByRole('link', { name: /作品/ }).click()
    await expect(page.getByRole('heading', { name: '保存下来的正文内容' })).toBeVisible()
    await expect(page.getByText('雨夜开场')).toBeVisible()
    await expectNoContrastViolations(page, '作品')

    await page.getByRole('link', { name: /资料库/ }).click()
    await expect(page.getByRole('navigation', { name: '资料库分类' })).toBeVisible()
    await expect(page.getByRole('link', { name: /导入资料/ })).toBeVisible()
    await expect(page.getByLabel('知识类型筛选')).toHaveCSS('background-color', 'rgb(52, 55, 53)')
    await expect(page.getByLabel('知识类型筛选').locator('option').first()).toHaveCSS('background-color', 'rgb(106, 73, 60)')
    await expectReadable(page.getByRole('navigation', { name: '资料库分类' }).getByRole('link', { name: /知识与资料/ }))
    await expectNoContrastViolations(page, '资料库')

    await page.getByRole('link', { name: /设置/ }).click()
    await expect(page.getByRole('navigation', { name: '设置分类' })).toBeVisible()
    await expectReadable(page.getByRole('navigation', { name: '设置分类' }).getByRole('link', { name: /模型与能力/ }))
    await expect(page.locator('.usage-panel strong')).toHaveText('今日 0 次请求 · 0 tokens')
    await expect(page.getByLabel('用量维度')).toHaveCSS('background-color', 'rgb(52, 55, 53)')
    await expectReadable(page.locator('.usage-panel strong'))
    await expectNoContrastViolations(page, '设置')
    await page.getByRole('link', { name: /项目与故事/ }).click()
    await expect(page.getByRole('button', { name: '删除项目' })).toBeVisible()
    await expect(page.getByRole('button', { name: '归档当前故事' })).toBeVisible()
  })

  test('资料导入页和会话资料托盘在窄屏与大屏没有横向溢出', async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-import', name: '导入项目', title: '导入项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-import/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-import', name: '导入故事', creation_mode: 'conversational' }] } } }))
    await page.route('**/api/v1/projects/p-import/stories/s-import/sessions', async (route) => route.fulfill({ json: { data: { sessions: [{ session_id: 'sess-import', title: '资料会话', status: 'active' }] } } }))
    await page.route('**/api/v1/projects/p-import/ingestion/workbench', async (route) => route.fulfill({ json: { data: { batch_rows: [], active_task_count: 0, failed_task_count: 0 } } }))
    await page.route('**/api/v1/projects/p-import/ingestion/attachments*', async (route) => route.fulfill({ json: { data: { attachments: [] } } }))
    await page.route('**/api/v1/projects/p-import/stories/s-import/sessions/sess-import', async (route) => route.fulfill({ json: { data: { session: { session_id: 'sess-import', title: '资料会话', status: 'active' }, turns: [], fragments: [], attachments: [] } } }))
    await page.route('**/api/v1/projects/p-import/stories/s-import/sessions/sess-import/actions', async (route) => route.fulfill({ json: { data: { actions: [] } } }))

    await page.setViewportSize({ width: 781, height: 945 })
    await page.goto('/conversational/library/research')
    await expect(page.getByRole('heading', { name: /粘贴资料或导入文件/ })).toBeVisible()
    await expect(page.getByText('项目资料', { exact: true })).toBeVisible()
    await expect(page.getByText('网络研究', { exact: true })).toHaveCount(0)
    await expect(page.getByText('URL', { exact: true })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
    await page.screenshot({ path: 'test-results/import-library-781x945.png', fullPage: true })

    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/conversational/session/sess-import')
    await expect(page.getByTitle('添加会话资料')).toBeVisible()
    await page.getByTitle('添加会话资料').click()
    await expect(page.getByRole('heading', { name: /把资料加入当前创作/ })).toBeVisible()
    await expect(page.getByLabel('资料类型')).toBeVisible()
    await expect(page.getByText('URL', { exact: true })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
    await page.screenshot({ path: 'test-results/import-session-1440x900.png', fullPage: true })
  })

  test('已归档故事可以恢复或永久删除，且不会混入当前故事选择器', async ({ page }) => {
    const stories = [
      { story_id: 's-active', name: '进行中故事', description: '', creation_mode: 'conversational', status: 'active' },
      { story_id: 's-restore', name: '等待恢复', description: '暂时收起', creation_mode: 'conversational', status: 'archived' },
      { story_id: 's-purge', name: '等待清理', description: '', creation_mode: 'conversational', status: 'archived' },
    ]
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-lifecycle', name: '生命周期项目', title: '生命周期项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-lifecycle/stories', async (route) => route.fulfill({ json: { data: { stories } } }))
    await page.route('**/api/v1/projects/p-lifecycle/stories/*/sessions', async (route) => route.fulfill({ json: { data: { sessions: [] } } }))
    await page.route('**/api/v1/projects/p-lifecycle/stories/s-restore/restore', async (route) => {
      stories.find((story) => story.story_id === 's-restore')!.status = 'active'
      await route.fulfill({ json: { data: { restored: true } } })
    })
    await page.route('**/api/v1/projects/p-lifecycle/stories/s-purge', async (route) => {
      stories.splice(stories.findIndex((story) => story.story_id === 's-purge'), 1)
      await route.fulfill({ json: { data: { deleted: true } } })
    })
    await page.goto('/conversational/settings?section=workspace')

    await expect(page.getByLabel('选择故事').locator('option')).toHaveCount(1)
    await expect(page.getByText('等待恢复', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '恢复', exact: true }).first().click()
    await expect(page.getByLabel('选择故事').locator('option')).toHaveCount(2)
    await expect(page.getByLabel('选择故事')).toHaveValue('s-restore')

    const purgeRow = page.locator('.archive-list li').filter({ hasText: '等待清理' })
    await purgeRow.getByRole('button', { name: '永久删除' }).click()
    const deleteDialog = page.getByRole('dialog', { name: '永久删除故事？' })
    await expect(deleteDialog).toBeVisible()
    await page.getByLabel('输入故事名称确认').fill('等待清理')
    await deleteDialog.getByRole('button', { name: '永久删除', exact: true }).click()
    await expect(page.getByText('等待清理', { exact: true })).toHaveCount(0)
    await expectNoContrastViolations(page, '归档故事管理')
  })

  test('作品页可以删除章节正文，或在保留来源对话时移出采用片段', async ({ page }) => {
    const items = [
      { id: 'chapter:1', kind: 'chapter', title: '第一章', subtitle: '已保存章节', preview: '章节正文', word_count: 4, updated_at: '2026-08-21T20:00:00+08:00', chapter_no: 1 },
      { id: 'fragment:one', kind: 'conversation_fragment', title: '雨夜开场', subtitle: '已采用片段', preview: '雨落在旧车站。', word_count: 7, updated_at: '2026-08-21T19:00:00+08:00', session_id: 'session-one', fragment_id: 'one' },
    ]
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-work-delete', name: '作品管理项目', title: '作品管理项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-work-delete/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-work-delete', name: '作品管理故事', creation_mode: 'conversational', status: 'active' }] } } }))
    await page.route('**/api/v1/projects/p-work-delete/stories/s-work-delete/sessions', async (route) => route.fulfill({ json: { data: { sessions: [] } } }))
    await page.route('**/api/v1/projects/p-work-delete/stories/s-work-delete/works*', async (route) => route.fulfill({ json: { data: { items, total: items.length, next_cursor: '' } } }))
    await page.route('**/api/v1/projects/p-work-delete/stories/s-work-delete/works/chapters/1', async (route) => {
      items.splice(items.findIndex((item) => item.id === 'chapter:1'), 1)
      await route.fulfill({ json: { data: { deleted: true } } })
    })
    await page.route('**/api/v1/projects/p-work-delete/stories/s-work-delete/works/fragments/one', async (route) => {
      items.splice(items.findIndex((item) => item.id === 'fragment:one'), 1)
      await route.fulfill({ json: { data: { removed: true } } })
    })
    await page.goto('/conversational/works')

    await page.getByRole('button', { name: '删除正文', exact: true }).click()
    await expect(page.getByRole('dialog', { name: /删除“第一章”的正文/ })).toContainText('章节大纲和相关对话仍会保留')
    await page.getByRole('button', { name: '删除正文', exact: true }).last().click()
    await expect(page.getByText('第一章', { exact: true })).toHaveCount(0)

    await page.getByRole('button', { name: '移出作品', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '从作品中移除这个片段？' })).toContainText('来源对话仍会保留')
    await page.getByRole('button', { name: '移出作品', exact: true }).last().click()
    await expect(page.getByText('还没有保存的作品')).toBeVisible()
  })

  test('作品服务未就绪时使用页面内中文状态，不暴露原始错误', async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-works-error', name: '作品错误项目', title: '作品错误项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-works-error/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-works-error', name: '作品错误故事', creation_mode: 'conversational' }] } } }))
    await page.route('**/api/v1/projects/p-works-error/stories/s-works-error/sessions', async (route) => route.fulfill({ json: { data: { sessions: [] } } }))
    await page.route('**/api/v1/projects/p-works-error/stories/s-works-error/works*', async (route) => route.fulfill({ status: 404, json: { error: { code: 'not_found', message: 'Not Found' } } }))
    await page.goto('/conversational/works')

    await expect(page.getByRole('alert')).toContainText('作品服务尚未就绪')
    await expect(page.getByRole('alert')).toContainText('请重启 NovelForge 后重新尝试')
    await expect(page.getByRole('button', { name: '重新尝试' })).toBeVisible()
    await expect(page.getByText('Not Found', { exact: true })).toHaveCount(0)
    await expectNoContrastViolations(page, '作品服务未就绪')
  })

  test('切换故事会重建编辑器并加载新故事内容', async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-context', name: '上下文项目', title: '上下文项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-context/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-context-a', name: '故事 A', creation_mode: 'planned' }, { story_id: 's-context-b', name: '故事 B', creation_mode: 'planned' }] } } }))
    await page.route('**/api/v1/projects/p-context/stories/*/profile', async (route) => route.fulfill({ json: { data: { profile: {} } } }))
    await page.route('**/api/v1/projects/p-context/stories/*/structure', async (route) => route.fulfill({ json: { data: { volumes: [], arcs: [], chapters: [] } } }))
    await page.route('**/api/v1/projects/p-context/stories/*/outline', async (route) => {
      const content = route.request().url().includes('s-context-b') ? '故事 B 的正式大纲' : '故事 A 的正式大纲'
      if (route.request().method() === 'GET') await route.fulfill({ json: { data: { content } } })
      else await route.fulfill({ json: { data: { content } } })
    })
    await page.goto('/planned/outline')
    await expect(page.locator('textarea').first()).toHaveValue('故事 A 的正式大纲')
    await page.getByLabel('选择故事').selectOption('s-context-b')
    await expect(page.locator('textarea').first()).toHaveValue('故事 B 的正式大纲')
  })

  test('重命名和危险操作使用工作台内弹窗', async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-dialog', name: '弹窗项目', title: '弹窗项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-dialog/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-dialog', name: '弹窗故事', creation_mode: 'planned' }] } } }))
    await page.goto('/')
    await page.getByRole('link', { name: /进入规划工作台/ }).click()
    const renameButton = page.getByRole('button', { name: '重命名故事' })
    await renameButton.click()
    await expect(page.getByRole('dialog', { name: '重命名故事' })).toBeVisible()
    await expect(page.getByLabel('故事名称')).toHaveValue('弹窗故事')
    await page.keyboard.press('Shift+Tab')
    await expect(page.getByRole('button', { name: '保存', exact: true })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: '重命名故事' })).toBeHidden()
    await expect(renameButton).toBeFocused()
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
      await expect(page.getByRole('link', { name: /选择规划模式/ })).toBeVisible()
      await expect(page.getByRole('link', { name: /选择对话模式/ })).toBeVisible()
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
      expect(overflow).toBe(false)
      await page.screenshot({ path: `test-results/mode-picker-${viewport.width}x${viewport.height}.png`, fullPage: true })
      await page.close()
    }
  })

  test('中文组合输入期间不会误触发发送，并可承载长草稿', async ({ page }) => {
    await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [{ project_id: 'p-ime', name: 'IME 项目', title: 'IME 项目' }], frontend_modes: ['planned', 'conversational'] } } }))
    await page.route('**/api/v1/projects/p-ime/stories', async (route) => route.fulfill({ json: { data: { stories: [{ story_id: 's-ime', name: 'IME 故事', creation_mode: 'conversational' }] } } }))
    let turnRequests = 0
    await page.route('**/api/v1/projects/p-ime/stories/s-ime/sessions', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ json: { data: { sessions: [{ session_id: 'sess-ime', title: 'IME 会话', status: 'active' }] } } })
        return
      }
      await route.fulfill({ json: { data: { session: { session_id: 'sess-ime', title: 'IME 会话', status: 'active' } } } })
    })
    await page.route('**/api/v1/projects/p-ime/stories/s-ime/sessions/sess-ime', async (route) => route.fulfill({ json: { data: { session: { session_id: 'sess-ime', title: 'IME 会话', status: 'active' }, turns: [], fragments: [], attachments: [] } } }))
    await page.route('**/api/v1/projects/p-ime/stories/s-ime/sessions/sess-ime/actions', async (route) => route.fulfill({ json: { data: { actions: [] } } }))
    await page.route('**/api/v1/projects/p-ime/stories/s-ime/sessions/sess-ime/turns/stream', async (route) => {
      turnRequests += 1
      await route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'event: done\ndata: {"result":{}}\n\n' })
    })
    await page.goto('/')
    await page.getByRole('link', { name: /进入对话工作台/ }).click()
    const composer = page.locator('textarea').first()
    await expect(composer).toBeVisible()
    await composer.dispatchEvent('compositionstart')
    await composer.fill('这是一段组合输入中的中文草稿')
    await composer.press('Control+Enter')
    expect(turnRequests).toBe(0)
    await composer.dispatchEvent('compositionend')
    await composer.press('Control+Enter')
    await expect.poll(() => turnRequests).toBe(1)
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
