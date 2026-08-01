export function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n < 0) {
    return '—'
  }
  if (n < 1024) {
    return `${n} B`
  }
  if (n < 1024 * 1024) {
    return `${(n / 1024).toFixed(1)} KiB`
  }
  if (n < 1024 * 1024 * 1024) {
    return `${(n / (1024 * 1024)).toFixed(1)} MiB`
  }
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GiB`
}

export function formatDateTime(iso: string): string {
  if (!iso) {
    return '—'
  }
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}
