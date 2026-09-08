import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import MaterialImportForm from './MaterialImportForm.vue'

const apiMock = vi.hoisted(() => ({
  addPastedAttachment: vi.fn(),
  addPastedIngestionText: vi.fn(),
  addFileAttachment: vi.fn(),
  uploadIngestionBatch: vi.fn(),
  previewOcr: vi.fn(),
}))
vi.mock('../api/client', () => ({ api: apiMock, ApiClientError: class ApiClientError extends Error { status = 500; code = 'test' } }))

const choose = async (wrapper: ReturnType<typeof mount>, files: File[]) => {
  const tab = wrapper.findAll('button').find((button) => button.text() === '导入文件')
  if (!tab) throw new Error('导入文件 tab not found')
  await tab.trigger('click')
  const input = wrapper.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: files })
  await input.trigger('change')
  await wrapper.get('button.button.accent').trigger('click')
  await flushPromises()
}

describe('MaterialImportForm', () => {
  it('rejects an oversized file before calling the API', async () => {
    apiMock.addFileAttachment.mockReset()
    const wrapper = mount(MaterialImportForm, { props: { projectId: 'project-1', storyId: 'story-1', sessionId: 'session-1', mode: 'session' } })
    const file = new File(['x'], 'oversized.pdf', { type: 'application/pdf' })
    Object.defineProperty(file, 'size', { configurable: true, value: 32 * 1024 * 1024 + 1 })
    await choose(wrapper, [file])
    expect(wrapper.text()).toContain('oversized.pdf 超过 32MB 单文件限制')
    expect(apiMock.addFileAttachment).not.toHaveBeenCalled()
  })

  it('keeps the request bound to the original story when the workspace changes mid-upload', async () => {
    let resolve!: (value: any) => void
    apiMock.addFileAttachment.mockReturnValueOnce(new Promise((res) => { resolve = res }))
    const wrapper = mount(MaterialImportForm, { props: { projectId: 'project-old', storyId: 'story-old', sessionId: 'session-1', branchId: 'branch-old', mode: 'session' } })
    const file = new File(['memo'], 'memo.txt', { type: 'text/plain' })
    const tab = wrapper.findAll('button').find((button) => button.text() === '导入文件')
    if (!tab) throw new Error('导入文件 tab not found')
    await tab.trigger('click')
    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await wrapper.get('button.button.accent').trigger('click')
    await wrapper.setProps({ projectId: 'project-new', storyId: 'story-new', branchId: 'branch-new' })
    resolve({ attachment: { attachment_id: 'old-attachment' }, warnings: [] })
    await flushPromises()
    expect(apiMock.addFileAttachment).toHaveBeenCalledWith('project-old', 'story-old', 'session-1', file, 'story', 'branch-old')
    expect(wrapper.text()).toContain('memo.txt')
  })

  it('uses one captured branch for every file in a session batch', async () => {
    apiMock.addFileAttachment.mockReset()
    let resolveFirst!: (value: any) => void
    apiMock.addFileAttachment
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce({ attachment: { attachment_id: 'second' }, warnings: [] })
    const wrapper = mount(MaterialImportForm, { props: { projectId: 'project-1', storyId: 'story-1', sessionId: 'session-1', branchId: 'branch-old', mode: 'session' } })
    const first = new File(['one'], 'one.txt', { type: 'text/plain' })
    const second = new File(['two'], 'two.txt', { type: 'text/plain' })
    const tab = wrapper.findAll('button').find((button) => button.text() === '导入文件')
    if (!tab) throw new Error('导入文件 tab not found')
    await tab.trigger('click')
    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [first, second] })
    await input.trigger('change')
    await wrapper.get('button.button.accent').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.setProps({ branchId: 'branch-new' })
    resolveFirst({ attachment: { attachment_id: 'first' }, warnings: [] })
    await flushPromises()
    expect(apiMock.addFileAttachment).toHaveBeenNthCalledWith(1, 'project-1', 'story-1', 'session-1', first, 'story', 'branch-old')
    expect(apiMock.addFileAttachment).toHaveBeenNthCalledWith(2, 'project-1', 'story-1', 'session-1', second, 'story', 'branch-old')
  })

  it('reports partial success and leaves failed files selected for retry', async () => {
    apiMock.addFileAttachment.mockReset()
    apiMock.addFileAttachment.mockResolvedValueOnce({ attachment: { attachment_id: 'ok' }, warnings: [] }).mockRejectedValueOnce(new Error('provider unavailable'))
    const wrapper = mount(MaterialImportForm, { props: { projectId: 'project-1', storyId: 'story-1', sessionId: 'session-1', mode: 'session' } })
    const first = new File(['one'], 'one.txt', { type: 'text/plain' })
    const second = new File(['two'], 'two.txt', { type: 'text/plain' })
    await choose(wrapper, [first, second])
    const payload = (wrapper.emitted('imported')?.[0]?.[0] || {}) as { count: number; failedCount: number }
    expect(payload.count).toBe(1)
    expect(payload.failedCount).toBe(1)
    expect(wrapper.text()).toContain('two.txt')
    expect(wrapper.text()).toContain('provider unavailable')
  })
})
