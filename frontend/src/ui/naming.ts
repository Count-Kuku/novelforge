/** 生成「项目N / 故事N」式的下一个编号建议名。
 *
 * 简单序号策略：在传入的名字列表中找形如 `{label}数字` 的最大编号，返回 +1；
 * 没有任何编号样式时从 1 开始。避免同屏出现两个「项目1」，也避免覆盖已有项目目录。
 */
export function suggestSequelName(label: string, existingNames: Array<string | null | undefined>): string {
  const prefix = label.toLowerCase()
  let maxNumber = 0
  for (const raw of existingNames) {
    const name = String(raw || '').trim()
    if (!name) continue
    const match = new RegExp(`^${label}(\\d+)$`).exec(name)
    if (match) {
      const parsed = Number(match[1])
      if (Number.isFinite(parsed) && parsed > maxNumber) maxNumber = parsed
    }
  }
  return `${label}${maxNumber + 1}`
}
