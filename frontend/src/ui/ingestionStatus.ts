const STATUS_LABELS: Record<string, string> = {
  queued: '等待中',
  running: '进行中',
  processing: '处理中',
  extracting: '提炼知识',
  completed: '已完成',
  indexed: '已完成',
  succeeded: '已完成',
  completed_with_errors: '部分完成',
  failed: '失败',
  error: '失败',
  retrying: '重试中',
  paused: '已暂停',
  cancelled: '已取消',
  waiting_model: '等待模型',
  model_unavailable: '模型不可用',
  capability_unavailable: '能力不可用',
  awaiting_confirmation: '等待费用确认',
  awaiting_cost_confirmation: '等待费用确认',
  blocked: '等待恢复',
}

const ACTIVE_STATUSES = new Set(['queued', 'running', 'processing', 'extracting', 'retrying'])
const RETRYABLE_STATUSES = new Set(['failed', 'error', 'capability_unavailable', 'awaiting_confirmation', 'awaiting_cost_confirmation', 'completed_with_errors', 'cancelled'])

export function ingestionStatus(item: any): string {
  return String(item?.task_status || item?.ingestion_status || item?.metadata?.background_status || item?.background_status || item?.status || 'indexed').toLowerCase()
}

export function ingestionStatusLabel(item: any): string {
  const status = ingestionStatus(item)
  return STATUS_LABELS[status] || status || '已登记'
}

export function ingestionStatusIsActive(item: any): boolean {
  return ACTIVE_STATUSES.has(ingestionStatus(item))
}

export function ingestionStatusCanRetry(item: any): boolean {
  return RETRYABLE_STATUSES.has(ingestionStatus(item))
}

export function ingestionProgressSuffix(item: any): string {
  const progress = item?.task_progress
  const pieces: string[] = []
  if (progress?.total != null) pieces.push(`${progress.completed || 0}/${progress.total} 项`)
  const blocked = Number(item?.blocked_count ?? item?.metadata?.blocked_count ?? 0)
  const confirmed = Number(item?.auto_confirmed_count ?? item?.metadata?.auto_confirmed_count ?? 0)
  if (blocked > 0) pieces.push(`${blocked} 条待恢复`)
  if (confirmed > 0) pieces.push(`${confirmed} 条已确认`)
  return pieces.length ? ` · ${pieces.join(' · ')}` : ''
}

function formatCost(value: unknown, currency: string): string {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return ''
  const symbol = currency === 'CNY' ? '¥' : currency === 'USD' ? '$' : `${currency} `
  return `${symbol}${amount < 0.01 ? amount.toFixed(4) : amount.toFixed(2)}`
}

export function ingestionEstimateLabel(estimate: any): string {
  const value = estimate && typeof estimate === 'object' ? estimate : {}
  const currency = String(value.display_currency || '').toUpperCase()
  const range = currency === 'CNY' ? value.cost_range_cny : value.cost_range_usd
  const calls = Number(value.estimated_model_calls || 0)
  let message = ''
  if (range && typeof range === 'object') {
    const low = formatCost(range.low, currency)
    const expected = formatCost(range.expected, currency)
    const high = formatCost(range.high, currency)
    if (low && high) message = `预计费用 ${low}–${high}${expected ? `（预期 ${expected}）` : ''}`
  }
  if (!message) message = '费用未知'
  return calls > 0 ? `${message}，预计调用 ${calls} 次` : message
}
