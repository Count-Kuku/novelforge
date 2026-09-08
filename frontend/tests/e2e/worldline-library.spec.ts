import { test, expect, type Page } from '@playwright/test'

const project = { project_id: 'p-worldline', name: '世界线项目', title: '世界线项目' }
const story = { story_id: 's-worldline', name: '同章故事', creation_mode: 'conversational', status: 'active' }
const mainBranch = {
  branch_id: 'branch-main', story_id: story.story_id, name: '主线', parent_branch_id: null,
  fork_fragment_id: null, head_checkpoint_id: 'checkpoint-main', status: 'active',
  revision: 3, is_default: true,
}

function sessionBundle(branchId: string, sessionId: string, extractionStatus = 'completed') {
  return {
    session: { session_id: sessionId, title: branchId === 'branch-main' ? '主线会话' : '获救线会话', status: 'active', branch_id: branchId, active_fragment_id: 'fragment-confirmed' },
    turns: [{ turn_id: `${sessionId}-turn`, user_message: '继续这一章', created_at: '2026-09-08T08:00:00Z' }],
    fragments: [{ fragment_id: 'fragment-confirmed', content: '她在旧车站找到了出口。', status: 'accepted', extraction_status: extractionStatus, created_at: '2026-09-08T08:01:00Z' }],
    attachments: [],
  }
}

async function routeWorkspace(page: Page, options: { withReference?: boolean; extractionStatus?: string; directChild?: boolean; delayDirectSession?: boolean } = {}) {
  const initialChild = { ...mainBranch, branch_id: 'branch-rescue', name: '获救线', parent_branch_id: mainBranch.branch_id, fork_fragment_id: 'fragment-confirmed', is_default: false, revision: 1 }
  let branches = options.directChild ? [mainBranch, initialChild] : [mainBranch]
  let activeBranchId = mainBranch.branch_id
  let sessions: Record<string, string> = { [mainBranch.branch_id]: 'session-main', ...(options.directChild ? { [initialChild.branch_id]: 'session-child' } : {}) }
  let binding: Record<string, unknown> | null = null
  let forkPayload: Record<string, unknown> | null = null

  await page.route('**/api/v1/bootstrap', async (route) => route.fulfill({ json: { data: { projects: [project], frontend_modes: ['planned', 'conversational'] } } }))
  await page.route(`**/api/v1/projects/${project.project_id}/stories`, async (route) => route.fulfill({ json: { data: { stories: [story] } } }))
  await page.route(new RegExp(`/api/v1/projects/${project.project_id}/stories/${story.story_id}/branches(?:/.*)?(?:\\?.*)?$`), async (route) => {
    const request = route.request()
    if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/fork')) {
      forkPayload = request.postDataJSON() as Record<string, unknown>
      const child = { ...mainBranch, branch_id: 'branch-rescue', name: String(forkPayload.name), parent_branch_id: mainBranch.branch_id, fork_fragment_id: String(forkPayload.fork_fragment_id), is_default: false, revision: 1 }
      branches = [...branches, child]
      activeBranchId = child.branch_id
      sessions[child.branch_id] = 'session-child'
      await route.fulfill({ json: { data: { branch: child, session: { session_id: 'session-child', title: '获救线会话', status: 'active', branch_id: child.branch_id }, context: {} } } })
      return
    }
    if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/checkpoints')) {
      await route.fulfill({ json: { data: { checkpoint: { checkpoint_id: 'checkpoint-skipped', frontier_fragment_id: 'fragment-confirmed', extraction_status: 'skipped' } } } })
      return
    }
    if (request.method() === 'PATCH') {
      const id = new URL(request.url()).pathname.split('/').at(-1)
      branches = branches.map((item) => item.branch_id === id ? { ...item, ...request.postDataJSON() } : item)
      await route.fulfill({ json: { data: { branch: branches.find((item) => item.branch_id === id) } } })
      return
    }
    await route.fulfill({ json: { data: { branches, active_branch_id: activeBranchId } } })
  })
  await page.route(`**/api/v1/projects/${project.project_id}/stories/${story.story_id}/sessions**`, async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path.endsWith('/actions')) {
      await route.fulfill({ json: { data: { actions: [] } } })
      return
    }
    if (path.endsWith('/sessions')) {
      const branchId = url.searchParams.get('branch_id') || mainBranch.branch_id
      const sessionId = sessions[branchId]
      await route.fulfill({ json: { data: { sessions: sessionId ? [{ session_id: sessionId, title: branchId === mainBranch.branch_id ? '主线会话' : '获救线会话', status: 'active', branch_id: branchId }] : [] } } })
      return
    }
    const sessionId = path.split('/').at(-1) || 'session-main'
    const branchId = sessionId === 'session-child' ? 'branch-rescue' : mainBranch.branch_id
    if (options.delayDirectSession) await new Promise((resolve) => setTimeout(resolve, 450))
    await route.fulfill({ json: { data: sessionBundle(branchId, sessionId, options.extractionStatus) } })
  })

  if (options.withReference) {
    await page.route(`**/api/v1/projects/${project.project_id}/ingestion/workbench`, async (route) => route.fulfill({ json: { data: { batch_rows: [], active_task_count: 0, failed_task_count: 0 } } }))
    await page.route(`**/api/v1/projects/${project.project_id}/ingestion/attachments*`, async (route) => route.fulfill({ json: { data: { attachments: [] } } }))
    await page.route(`**/api/v1/projects/${project.project_id}/reference-libraries`, async (route) => route.fulfill({ json: { data: { libraries: [{ library_id: 'library-map', title: '地图资料', project_id: project.project_id }] } } }))
    await page.route(`**/api/v1/projects/${project.project_id}/reference-libraries/library-map/releases`, async (route) => route.fulfill({ json: { data: { releases: [{ release_id: 'release-map-1', release_no: 1, status: 'ready', manifest_json: JSON.stringify({ item_count: 4 }) }] } } }))
    await page.route(`**/api/v1/projects/${project.project_id}/reference-libraries/library-map/releases/release-map-1/sources`, async (route) => route.fulfill({ json: { data: { library_id: 'library-map', release_id: 'release-map-1', sources: [{ source_id: 'source-map', revision_id: 'revision-map-1', source_json: { title: '地图原文' }, content_hash_verified: true }] } } }))
    await page.route(`**/api/v1/projects/${project.project_id}/stories/${story.story_id}/reference-libraries*`, async (route) => route.fulfill({ json: { data: { bindings: binding ? [binding] : [] } } }))
    await page.route(`**/api/v1/projects/${project.project_id}/stories/${story.story_id}/reference-libraries/library-map/bindings`, async (route) => {
      binding = { binding_id: 'binding-map-1', library_id: 'library-map', release_id: 'release-map-1', branch_id: 'branch-main', status: 'active' }
      await route.fulfill({ json: { data: { binding } } })
    })
    await page.route(`**/api/v1/projects/${project.project_id}/stories/${story.story_id}/reference-libraries/bindings/binding-map-1*`, async (route) => {
      binding = null
      await route.fulfill({ json: { data: { binding: { binding_id: 'binding-map-1', status: 'unbound' }, unbound: true } } })
    })
  }

  return {
    get forkPayload() { return forkPayload },
  }
}

test.describe('世界线与资料副本用户流程', () => {
  test('直达子线会话先解析所属世界线，不被最近主线会话覆盖', async ({ page }) => {
    await routeWorkspace(page, { directChild: true })
    await page.goto('/conversational/session/session-child')
    await expect(page.getByLabel('选择世界线')).toHaveValue('branch-rescue')
    await expect(page.getByRole('heading', { name: '获救线会话' })).toBeVisible()
  })

  test('从已确认片段分叉后切换世界线，并进入继承的新会话', async ({ page }) => {
    const state = await routeWorkspace(page)
    await page.goto('/conversational/session/session-main')
    await expect(page.getByLabel('选择世界线')).toHaveValue('branch-main')
    await expect(page.locator('.fragment-card p').filter({ hasText: '她在旧车站找到了出口。' }).first()).toBeVisible()

    await page.getByRole('button', { name: '从选定片段创建世界线' }).click()
    const dialog = page.getByRole('dialog', { name: '从已确认片段创建世界线' })
    await dialog.getByLabel('世界线名称').fill('获救线')
    await dialog.getByRole('button', { name: '创建并切换' }).click()

    await expect.poll(() => state.forkPayload).toMatchObject({ name: '获救线', fork_fragment_id: 'fragment-confirmed' })
    await expect(page.getByLabel('选择世界线')).toHaveValue('branch-rescue')
    await expect(page.getByLabel('选择世界线').locator('option', { hasText: '获救线' })).toHaveCount(1)
    await expect(page).toHaveURL(/\/conversational\/session\/session-child$/)
    await expect(page.getByRole('heading', { name: '获救线会话' })).toBeVisible()
  })

  test('用户主动切换世界线后不会被旧直达会话请求切回', async ({ page }) => {
    await routeWorkspace(page, { directChild: true, delayDirectSession: true })
    await page.goto('/conversational/session/session-child')
    await expect(page.getByLabel('选择世界线')).toBeVisible()
    await expect(page.getByLabel('选择世界线')).toHaveValue('branch-rescue')
    await page.getByLabel('选择世界线').selectOption('branch-main')
    await expect(page.getByLabel('选择世界线')).toHaveValue('branch-main')
    await expect(page.getByRole('heading', { name: '主线会话' })).toBeVisible()
  })

  test('未提炼片段必须先明确跳过并封存检查点，不能隐式使用当前状态', async ({ page }) => {
    const state = await routeWorkspace(page, { extractionStatus: 'pending' })
    await page.goto('/conversational/session/session-main')
    await page.getByRole('button', { name: '从选定片段创建世界线' }).click()
    const skipDialog = page.getByRole('dialog', { name: '片段尚未提炼' })
    await skipDialog.getByRole('button', { name: '跳过提炼并创建' }).click()
    const nameDialog = page.getByRole('dialog', { name: '从已确认片段创建世界线' })
    await nameDialog.getByLabel('世界线名称').fill('封存线')
    await nameDialog.getByRole('button', { name: '创建并切换' }).click()
    await expect.poll(() => state.forkPayload).toMatchObject({ name: '封存线', fork_checkpoint_id: 'checkpoint-skipped' })
    await expect.poll(() => state.forkPayload).not.toHaveProperty('allow_current_state')
  })

  test('资料副本用于当前故事后可解除使用，且加载失败会显示明确错误', async ({ page }) => {
    await routeWorkspace(page, { withReference: true })
    await page.goto('/conversational/library/research')
    await expect(page.getByRole('heading', { name: '用于当前故事' })).toBeVisible()
    await expect(page.getByText('地图资料')).toBeVisible()
    await page.getByRole('button', { name: '查看来源' }).click()
    await expect(page.getByText('地图原文 · 已校验')).toBeVisible()
    await page.getByRole('button', { name: '用于当前故事' }).click()
    await expect(page.getByText('已用于当前故事')).toBeVisible()
    await expect(page.getByText('已将“地图资料”复制为当前故事的私有副本。')).toBeVisible()

    await page.getByRole('button', { name: '解除使用' }).click()
    const dialog = page.getByRole('dialog', { name: '解除当前故事使用？' })
    await dialog.getByRole('button', { name: '解除使用' }).click()
    await expect(page.getByText('已解除当前故事使用，私有副本历史仍保留。')).toBeVisible()
    await expect(page.getByRole('button', { name: '用于当前故事' })).toBeVisible()
  })
})
