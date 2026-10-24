export function formatBer(value: number, digits = 3) {
  return value === 0 ? '0' : value.toExponential(digits)
}

export function formatMetric(value: number, digits = 4) {
  return Number.isFinite(value) ? value.toFixed(digits) : '—'
}
