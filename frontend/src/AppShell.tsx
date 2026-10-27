import type { ReactNode } from 'react'
import './AppShell.css'
import './DataViz.css'

type Stage = { path: string; label: string; short: string }

const stages: Stage[] = [
  { path: '/', label: 'Stage01 仿真', short: '01' },
  { path: '/stage02', label: 'Stage02 故障诊断', short: '02' },
  { path: '/stage03', label: 'Stage03 诊断挑战', short: '03' },
  { path: '/stage04', label: 'Stage04 频偏诊断', short: '04' },
  { path: '/stage05', label: 'Stage05 联合诊断', short: '05' },
  { path: '/stage06', label: 'Stage06 载波相位', short: '06' },
  { path: '/stage07', label: 'Stage07 三故障', short: '07' },
  { path: '/stage08', label: 'Stage08 定时同步', short: '08' },
  { path: '/stage09', label: 'Stage09 多径均衡', short: '09' },
  { path: '/stage10', label: 'Stage10 卷积编码', short: '10' },
  { path: '/stage11', label: 'Stage11 突发交织', short: '11' },
]

export default function AppShell({ route, children }: { route: string; children: ReactNode }) {
  const current = stages.find(stage => stage.path === route) ?? stages[0]
  return (
    <div className="app-shell">
      <nav className="app-nav" aria-label="实验阶段导航">
        <a className="app-brand" href="#/" aria-label="CommDoctor 首页">
          <span className="app-brand-mark">CD</span>
          <span>CommDoctor</span>
        </a>
        <div className="app-nav-links">
          {stages.map(stage => (
            <a
              key={stage.path}
              href={`#${stage.path}`}
              className={stage.path === current.path ? 'is-current' : undefined}
              aria-current={stage.path === current.path ? 'page' : undefined}
            >
              <span className="app-nav-number">{stage.short}</span>
              <span>{stage.label.replace(/^Stage\d+ /, '')}</span>
            </a>
          ))}
        </div>
      </nav>
      <div className="app-stage-bar" aria-live="polite">
        <span>当前实验</span><strong>{current.label}</strong>
        <span className="app-stage-hint">按阶段顺序完成：观察 → 测量 → 诊断 → 补偿 → 复盘</span>
      </div>
      {children}
    </div>
  )
}
