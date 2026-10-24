import type { ReactNode } from 'react'

export type MetricItem = {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'default' | 'accent' | 'good' | 'warning'
}

export function MetricCard({ label, value, hint, tone = 'default' }: MetricItem) {
  return (
    <article className={`cd-metric cd-metric-${tone}`}>
      <span className="cd-metric-label">{label}</span>
      <strong className="cd-metric-value">{value}</strong>
      {hint && <span className="cd-metric-hint">{hint}</span>}
    </article>
  )
}

export function MetricGrid({ items, className = '' }: { items: MetricItem[]; className?: string }) {
  return <div className={`cd-metric-grid ${className}`.trim()}>{items.map(item => <MetricCard key={item.label} {...item} />)}</div>
}

export function ChartLegend({ items }: { items: { label: string; color: string; marker?: 'line' | 'dot' }[] }) {
  return <div className="cd-chart-legend" aria-label="图例">{items.map(item => <span key={item.label}><i className={`cd-legend-marker ${item.marker ?? 'dot'}`} style={{ backgroundColor: item.color }} aria-hidden="true" />{item.label}</span>)}</div>
}

export function ChartFrame({
  title,
  xLabel,
  yLabel,
  description,
  legend,
  children,
  className = '',
}: {
  title: string
  xLabel: string
  yLabel: string
  description?: string
  legend?: { label: string; color: string; marker?: 'line' | 'dot' }[]
  children: ReactNode
  className?: string
}) {
  return (
    <figure className={`cd-chart-frame ${className}`.trim()}>
      <figcaption>
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </figcaption>
      <div className="cd-chart-area">
        <span className="cd-axis-label cd-axis-y">{yLabel}</span>
        <div className="cd-chart-svg">{children}<span className="cd-axis-label cd-axis-x">{xLabel}</span></div>
      </div>
      {legend && <ChartLegend items={legend} />}
    </figure>
  )
}
