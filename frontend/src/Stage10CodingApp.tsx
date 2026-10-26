import { useState } from 'react'
import './App.css'
import './Stage10Coding.css'
import { apiRequest } from './api'
import { ChartFrame, MetricGrid } from './DataViz'
import { formatBer } from './dataVizUtils'

type Experiment = {
  parameters: { n_information_bits: number; eb_n0_db: number; seed: number; include_details: boolean }
  code: { constraint_length: number; generators_octal: number[]; output_order: string[]; rate: number }
  energy: { eb_info: number; noise_variance: number; noise_std: number; coded_symbol_energy: number }
  lengths: { information_bits: number; tail_bits: number; encoded_bits: number; encoded_symbols: number; decoded_information_bits: number; effective_frame_rate: number }
  results: { uncoded_information: Ber; coded_channel: Ber; decoded_information: Ber & { correctly_recovered: boolean; decoded_tail_bits: number[] } }
  details: { included: boolean; window_information_bits: number; window_encoded_bits: number; truncated: boolean; information_bits: number[]; encoded_bits: number[]; uncoded_received: number[]; uncoded_hard_decisions: number[]; coded_received: number[]; coded_hard_decisions: number[]; decoded_information_bits: number[] }
  teaching: { encoding: string; channel: string; decoding: string; comparison: string; limitation: string }
}
type Ber = { errors: number; compared: number; ber: number }
type SweepMeasure = Ber
type SweepPoint = { eb_n0_db: number; seed: number; noise_variance: number; uncoded_information: SweepMeasure; coded_channel: SweepMeasure; decoded_information: SweepMeasure }
type Sweep = {
  parameters: { start_db: number; stop_db: number; step_db: number; n_information_bits: number; seed: number; point_count: number; total_information_bits: number }
  sampling: { design: string; repetitions_per_point: number; zero_error_note: string }
  points: SweepPoint[]
}

export default function Stage10CodingApp() {
  const [count, setCount] = useState('256')
  const [snr, setSnr] = useState('4')
  const [seed, setSeed] = useState('2026')
  const [details, setDetails] = useState(false)
  const [experiment, setExperiment] = useState<Experiment | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sweepStart, setSweepStart] = useState('0')
  const [sweepStop, setSweepStop] = useState('10')
  const [sweepStep, setSweepStep] = useState('2')
  const [sweepCount, setSweepCount] = useState('2048')
  const [sweepSeed, setSweepSeed] = useState('2026')
  const [sweep, setSweep] = useState<Sweep | null>(null)
  const [sweepBusy, setSweepBusy] = useState(false)
  const [sweepError, setSweepError] = useState('')

  const run = async () => {
    if (details && Number(count) > 256) { setError('完整比特细节最多支持 256 个信息位；请关闭细节显示或调低比特数。'); return }
    if (!Number.isInteger(Number(count)) || Number(count) < 1 || Number(count) > 4096) { setError('信息比特数必须是 1 到 4096 之间的整数。'); return }
    if (!Number.isFinite(Number(snr)) || Number(snr) < -10 || Number(snr) > 30) { setError('Eb/N₀ 必须在 −10 到 30 dB 之间。'); return }
    if (!Number.isInteger(Number(seed)) || Number(seed) < 0 || Number(seed) > 4294967295) { setError('随机种子必须是 0 到 4294967295 之间的整数。'); return }
    setBusy(true); setError('')
    try {
      const next = await apiRequest<Experiment>('/api/stage10/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ n_information_bits: Number(count), eb_n0_db: Number(snr), seed: Number(seed), include_details: details }) })
      setExperiment(next)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '实验失败，请检查参数后重试。') }
    finally { setBusy(false) }
  }

  const runSweep = async () => {
    const start = Number(sweepStart), stop = Number(sweepStop), step = Number(sweepStep)
    const n = Number(sweepCount), rootSeed = Number(sweepSeed)
    const intervals = (stop - start) / step
    const pointCount = Math.round(intervals) + 1
    if (![start, stop, step].every(Number.isFinite) || start < -10 || stop > 30 || stop <= start || step <= 0 || Math.abs(intervals - Math.round(intervals)) > 1e-9) { setSweepError('扫描范围必须递增、端点在 −10 至 30 dB 内，并能被步长整除。'); return }
    if (pointCount < 2 || pointCount > 16) { setSweepError('扫描必须包含 2 到 16 个 Eb/N₀ 点。'); return }
    if (!Number.isInteger(n) || n < 1 || n > 4096) { setSweepError('每点信息位数必须是 1 到 4096 之间的整数。'); return }
    if (pointCount * n > 32768) { setSweepError('总计算量不能超过 32768 个信息位；请减少点数或每点位数。'); return }
    if (!Number.isInteger(rootSeed) || rootSeed < 0 || rootSeed > 4294967295) { setSweepError('随机种子必须是 0 到 4294967295 之间的整数。'); return }
    setSweepBusy(true); setSweepError('')
    try {
      const next = await apiRequest<Sweep>('/api/stage10/ber-sweep', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ start_db: start, stop_db: stop, step_db: step, n_information_bits: n, seed: rootSeed }) })
      setSweep(next)
    } catch (cause) { setSweepError(cause instanceof Error ? cause.message : '性能扫描失败，请检查参数后重试。') }
    finally { setSweepBusy(false) }
  }

  return <div className="app">
    <header className="header stage10-header"><p className="stage10-eyebrow">CHANNEL CODING / 10</p><h1>卷积编码与 Viterbi 实验室</h1><p className="subtitle">在相同信息位能量预算下，观察冗余、噪声与路径译码如何影响误码</p></header>
    <main className="container stage10-container">
      <section className="stage10-intro"><div><span className="stage10-kicker">K = 3 · (7,5) · R = 1/2</span><h2>运行一次可重放的信道实验</h2><p>输入信息比特数、Eb/N₀ 和随机种子。每次实验使用同一组信息位比较未编码链路与卷积编码链路。</p></div>
        <form className="stage10-controls" onSubmit={event => { event.preventDefault(); void run() }}>
          <label htmlFor="stage10-count">信息比特数 <small>1–4096</small></label><input id="stage10-count" type="number" min="1" max="4096" step="1" value={count} onChange={event => setCount(event.target.value)} required />
          <label htmlFor="stage10-snr">信息位 Eb/N₀ <small>dB，−10 至 30</small></label><input id="stage10-snr" type="number" min="-10" max="30" step="0.1" value={snr} onChange={event => setSnr(event.target.value)} required />
          <label htmlFor="stage10-seed">随机种子</label><input id="stage10-seed" type="number" min="0" max="4294967295" step="1" value={seed} onChange={event => setSeed(event.target.value)} required />
          <label className="stage10-detail-toggle"><input type="checkbox" checked={details} onChange={event => setDetails(event.target.checked)} />显示完整比特细节 <small>最多 256 位</small></label>
          <button className="stage10-primary" type="submit" disabled={busy}>{busy ? '正在运行实验…' : experiment ? '使用当前参数重新运行' : '运行实验'}</button>
        </form>
      </section>
      <section className="stage10-panel stage10-sweep-controls">
        <div className="stage10-heading"><div><h2>多 Eb/N₀ 性能扫描</h2><p className="stage10-note">每个采样点运行一次独立、可复现的生产实验；最多 16 点、每点 4096 位、总计 32768 位。</p></div></div>
        <form className="stage10-controls" onSubmit={event => { event.preventDefault(); void runSweep() }}>
          <label htmlFor="stage10-sweep-start">起始 Eb/N₀ <small>dB，−10 至 30</small></label><input id="stage10-sweep-start" type="number" min="-10" max="30" step="0.1" value={sweepStart} onChange={event => setSweepStart(event.target.value)} required />
          <label htmlFor="stage10-sweep-stop">结束 Eb/N₀ <small>dB，须大于起点</small></label><input id="stage10-sweep-stop" type="number" min="-10" max="30" step="0.1" value={sweepStop} onChange={event => setSweepStop(event.target.value)} required />
          <label htmlFor="stage10-sweep-step">扫描步长 <small>dB，范围须整除</small></label><input id="stage10-sweep-step" type="number" min="0.1" max="40" step="0.1" value={sweepStep} onChange={event => setSweepStep(event.target.value)} required />
          <label htmlFor="stage10-sweep-count">每点信息位数 <small>1–4096</small></label><input id="stage10-sweep-count" type="number" min="1" max="4096" step="1" value={sweepCount} onChange={event => setSweepCount(event.target.value)} required />
          <label htmlFor="stage10-sweep-seed">随机种子 <small>0–4294967295</small></label><input id="stage10-sweep-seed" type="number" min="0" max="4294967295" step="1" value={sweepSeed} onChange={event => setSweepSeed(event.target.value)} required />
          <button className="stage10-primary" type="submit" disabled={sweepBusy}>{sweepBusy ? '正在计算性能曲线…' : sweep ? '使用当前参数重新扫描' : '运行 BER 性能扫描'}</button>
        </form>
        {sweepError && <div className="stage10-error" role="alert">{sweepError}</div>}
      </section>
      {sweep && <SweepResults sweep={sweep} />}
      <div className="stage10-strip"><span>同一信息位 Eb/N₀</span><span>实值 AWGN</span><span>硬判决 Viterbi</span><span>两个零尾位不计入信息 BER</span></div>
      {error && <div className="stage10-error" role="alert">{error}</div>}
      {!experiment && !error && <section className="stage10-empty"><h2>等待实验运行</h2><p>默认使用 256 个信息位与固定种子。BER 按完整有效帧统计；比特细节仅用于有限长度的教学预览。</p></section>}
      {experiment && <>
        <section className="stage10-panel"><div className="stage10-heading"><div><span className="stage10-kicker">01 / BER</span><h2>误码率对比</h2></div><span className="stage10-badge">{experiment.parameters.n_information_bits} 信息位 · seed {experiment.parameters.seed}</span></div>
          <MetricGrid items={[{ label: '未编码 BER', value: formatBer(experiment.results.uncoded_information.ber), hint: `${experiment.results.uncoded_information.errors} / ${experiment.results.uncoded_information.compared} 个信息位` }, { label: '编码接收 BER', value: formatBer(experiment.results.coded_channel.ber), hint: `${experiment.results.coded_channel.errors} / ${experiment.results.coded_channel.compared} 个码位（含尾位）` }, { label: '译码后信息 BER', value: formatBer(experiment.results.decoded_information.ber), hint: `${experiment.results.decoded_information.errors} / ${experiment.results.decoded_information.compared} 个信息位`, tone: 'good' }]} />
          <BerBars results={experiment.results} />
        </section>
        <section className="stage10-panel"><div className="stage10-heading"><div><span className="stage10-kicker">02 / SIGNAL CHAIN</span><h2>从信息位到译码结果</h2></div><span className="stage10-badge">信息位预览 {experiment.details.window_information_bits} 位</span></div>
          <MetricGrid items={[{ label: '码字长度', value: experiment.lengths.encoded_bits, hint: `信息位 ${experiment.lengths.information_bits} + 尾位 ${experiment.lengths.tail_bits}` }, { label: '编码符号能量', value: experiment.energy.coded_symbol_energy.toFixed(3), hint: `未编码符号能量 ${experiment.energy.eb_info.toFixed(2)}` }, { label: '噪声方差 σ²', value: experiment.energy.noise_variance.toPrecision(4), hint: `标准差 σ = ${experiment.energy.noise_std.toPrecision(4)}` }, { label: '译码终态', value: `零状态 · ${experiment.results.decoded_information.correctly_recovered ? '无信息误码' : '有信息误码'}`, hint: `回溯尾位 [${experiment.results.decoded_information.decoded_tail_bits.join(', ')}]` }]} />
          <BitsPanel experiment={experiment} />
          {experiment.details.truncated && <p className="stage10-note">序列较长，图中只显示前 {experiment.details.window_information_bits} 个信息位；所有 BER 仍按完整帧计算。</p>}
        </section>
        <section className="stage10-panel stage10-review"><div className="stage10-heading"><div><span className="stage10-kicker">03 / REVIEW</span><h2>本次实验复盘</h2></div><span className="stage10-badge">真实样本</span></div><div className="stage10-lesson"><p>{experiment.teaching.encoding}</p><p>{experiment.teaching.channel}</p><p>{experiment.teaching.decoding}</p><p><strong>本轮观察：</strong>{experiment.teaching.comparison}</p><p><strong>结果边界：</strong>{experiment.teaching.limitation}</p></div></section>
      </>}
    </main>
  </div>
}

function BerBars({ results }: { results: Experiment['results'] }) {
  const values = [results.uncoded_information.ber, results.coded_channel.ber, results.decoded_information.ber]
  const max = Math.max(...values, 0.001)
  const labels = ['未编码信息', '编码接收码位', '译码后信息']
  const colors = ['#e9a568', '#38bdf8', '#6ee7b7']
  return <ChartFrame title="三类 BER" description="编码通道 BER 的分母是全部码位；信息 BER 的分母是原始信息位数。" xLabel="链路阶段" yLabel="BER" className="stage10-chart">{<svg viewBox="0 0 600 190" role="img" aria-label="未编码、编码接收和译码后 BER 对比"><line x1="20" y1="150" x2="580" y2="150" stroke="#344256" />{values.map((value, index) => { const height = value === 0 ? 0 : Math.max(2, value / max * 112); const x = 90 + index * 175; return <g key={labels[index]}><rect x={x} y={150 - height} width="82" height={height} rx="6" fill={colors[index]} /><text x={x + 41} y="173" textAnchor="middle" fill="#d1d5db" fontSize="12">{labels[index]}</text><text x={x + 41} y={Math.max(18, 140 - height)} textAnchor="middle" fill="#d1d5db" fontSize="11">{formatBer(value)}</text></g> })}</svg>}</ChartFrame>
}

function SweepResults({ sweep }: { sweep: Sweep }) {
  const first = sweep.points[0]
  const last = sweep.points[sweep.points.length - 1]
  const decoded = sweep.points.map(point => point.decoded_information.ber)
  const nonMonotonic = decoded.some((value, index) => index > 0 && value > decoded[index - 1])
  const zeroCount = sweep.points.filter(point => point.decoded_information.errors === 0).length
  return <>
    <section className="stage10-panel" aria-labelledby="stage10-sweep-results-title">
      <div className="stage10-heading"><div><h2 id="stage10-sweep-results-title">BER 性能曲线</h2><p className="stage10-note">{sweep.parameters.point_count} 个独立实验点 · {sweep.parameters.n_information_bits} 信息位/点 · 根种子 {sweep.parameters.seed}</p></div><span className="stage10-badge">实测数据</span></div>
      <MetricGrid items={[
        { label: '扫描范围', value: `${first.eb_n0_db}–${last.eb_n0_db} dB`, hint: `步长 ${sweep.parameters.step_db} dB · ${sweep.parameters.point_count} 点` },
        { label: '每点样本量', value: sweep.parameters.n_information_bits, hint: `总计 ${sweep.parameters.total_information_bits} 个信息位` },
        { label: '译码 BER 零误码点', value: `${zeroCount} / ${sweep.points.length}`, hint: '保留实际 BER=0' },
      ]} />
      <SweepChart sweep={sweep} />
      <div className="stage10-table-wrap" tabIndex={0} role="region" aria-label="BER 扫描数据表，可横向滚动查看全部统计列">
        <table className="stage10-sweep-table">
          <caption>各 Eb/N₀ 点的真实误码数、统计分母和 BER</caption>
          <thead><tr><th scope="col">Eb/N₀ (dB)</th><th scope="col">噪声方差 σ²</th><th scope="col">未编码信息 errors / bits</th><th scope="col">未编码 BER</th><th scope="col">编码接收 errors / coded bits</th><th scope="col">编码接收 BER</th><th scope="col">Viterbi 信息 errors / bits</th><th scope="col">译码 BER</th></tr></thead>
          <tbody>{sweep.points.map(point => <tr key={point.eb_n0_db}>
            <th scope="row">{point.eb_n0_db}</th><td>{point.noise_variance.toPrecision(5)}</td>
            <td>{point.uncoded_information.errors} / {point.uncoded_information.compared}</td><td>{formatBer(point.uncoded_information.ber)}</td>
            <td>{point.coded_channel.errors} / {point.coded_channel.compared}</td><td>{formatBer(point.coded_channel.ber)}</td>
            <td>{point.decoded_information.errors} / {point.decoded_information.compared}</td><td>{formatBer(point.decoded_information.ber)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="stage10-note">每个 BER 均由该点实际误码数除以对应分母计算。编码接收 BER 统计含尾位的全部编码符号；译码 BER 仅统计原始信息位。各点各运行一次，不对 BER 百分比作简单平均。</p>
    </section>
    <section className="stage10-panel stage10-review" aria-labelledby="stage10-sweep-review-title">
      <div className="stage10-heading"><div><h2 id="stage10-sweep-review-title">本次扫描复盘</h2></div><span className="stage10-badge">{sweep.sampling.repetitions_per_point} 次/点</span></div>
      <div className="stage10-lesson">
        <p>本次测得 Eb/N₀ 从 {first.eb_n0_db} dB 到 {last.eb_n0_db} dB，实噪声方差从 {first.noise_variance.toPrecision(4)} 降至 {last.noise_variance.toPrecision(4)}。Eb/N₀ 越高，给定单位信息位能量下噪声越弱。</p>
        <p>K=3、R=1/2 卷积码为信息序列增加约一倍码位冗余，Viterbi 在四状态 trellis 上比较整段合法路径，利用跨时刻约束恢复信息。</p>
        <p>本轮译码 BER{nonMonotonic ? '出现了上升采样点' : '没有出现上升采样点'}；每点只有一次有限长度的独立 payload 和噪声实验，随机起伏会让曲线不单调。不同 payload 也意味着各点是性能样本而非逐位配对比较。</p>
        <p>有限样本中，编码 BER 不保证每个点都低于未编码 BER：误码具有随机性，码位 BER 与信息位 BER 的对象和分母也不同。只应比较各自定义明确的统计量。</p>
        <p>{zeroCount > 0 ? `本次有 ${zeroCount} 个译码零误码点，表中的真实测量值为 0。` : '本次没有译码零误码点。'} 零误码仅表示有限样本中未观察到错误，不能证明真实 BER 为零；本曲线是本次数据，不构成普遍性能保证。</p>
      </div>
    </section>
  </>
}

function SweepChart({ sweep }: { sweep: Sweep }) {
  const series: { key: keyof Pick<SweepPoint, 'uncoded_information' | 'coded_channel' | 'decoded_information'>; label: string; color: string }[] = [
    { key: 'uncoded_information', label: '未编码接收信息 BER', color: '#e9a568' },
    { key: 'coded_channel', label: '编码后接收硬判决 BER', color: '#38bdf8' },
    { key: 'decoded_information', label: 'Viterbi 译码信息 BER', color: '#6ee7b7' },
  ]
  const positive = sweep.points.flatMap(point => series.map(item => point[item.key].ber).filter(value => value > 0))
  const lowestExponent = Math.min(-3, positive.length ? Math.floor(Math.log10(Math.min(...positive))) - 1 : -3)
  const x = (index: number) => 46 + index * 510 / Math.max(sweep.points.length - 1, 1)
  const y = (value: number) => 20 + (-Math.log10(value)) / -lowestExponent * 132
  const ticks = Array.from({ length: -lowestExponent + 1 }, (_, index) => 10 ** -index)
  return <ChartFrame title="三条 BER 曲线（对数纵轴）" description="对数轴只绘制非零 BER；零误码点在图框下沿用空心三角单独标出，数值仍为 0。" xLabel="Eb/N₀（dB）" yLabel="BER（对数刻度）" legend={series.map(({ label, color }) => ({ label, color, marker: 'line' }))} className="stage10-chart stage10-sweep-chart">
    <svg viewBox="0 0 600 220" role="img" aria-label={`Eb/N0 ${sweep.points.map(point => point.eb_n0_db).join(', ')} dB 的三条实测 BER 曲线；零误码点在对数曲线下沿单独标记`}>
      {ticks.map(value => { const yy = y(value); return <g key={value}><line x1="40" y1={yy} x2="565" y2={yy} stroke="#344256" strokeDasharray="3 4" /><text x="35" y={yy + 4} textAnchor="end" fill="#cbd5e1" fontSize="10">{formatBer(value)}</text></g> })}
      {series.map(({ key, color, label }) => {
        const segments: string[] = []
        let segment: string[] = []
        sweep.points.forEach((point, index) => {
          const value = point[key].ber
          if (value > 0) segment.push(`${segment.length ? 'L' : 'M'} ${x(index)} ${y(value)}`)
          else { if (segment.length) segments.push(segment.join(' ')); segment = [] }
        })
        if (segment.length) segments.push(segment.join(' '))
        return <g key={key} aria-label={label}>
          {segments.map((path, index) => <path key={index} d={path} fill="none" stroke={color} strokeWidth="2.2" />)}
          {sweep.points.map((point, index) => {
            const measure = point[key]
            return measure.ber === 0
              ? <g key={point.eb_n0_db}><path d={`M ${x(index) - 5} 169 L ${x(index) + 5} 169 L ${x(index)} 160 Z`} fill="none" stroke={color} strokeWidth="1.8"><title>{label}: 0 errors / {measure.compared}, BER 0</title></path></g>
              : <circle key={point.eb_n0_db} cx={x(index)} cy={y(measure.ber)} r="4" fill={color}><title>{label}: {measure.errors} / {measure.compared}, BER {measure.ber}</title></circle>
          })}
        </g>
      })}
      {sweep.points.map((point, index) => <g key={point.eb_n0_db}><line x1={x(index)} y1="153" x2={x(index)} y2="157" stroke="#94a3b8"/><text x={x(index)} y="190" textAnchor="middle" fill="#cbd5e1" fontSize="10">{point.eb_n0_db}</text></g>)}
      <text x="570" y="168" fill="#cbd5e1" fontSize="9">△ 零误码</text>
    </svg>
  </ChartFrame>
}

function BitsPanel({ experiment }: { experiment: Experiment }) {
  const d = experiment.details
  const rows = [{ label: '信息位', value: d.information_bits.map(String).join('') }, { label: '编码码字', value: d.encoded_bits.map(String).join('') }, { label: '未编码接收样本', value: d.uncoded_received.slice(0, 24).map(value => value.toFixed(2)).join(' · ') }, { label: '未编码硬判决', value: d.uncoded_hard_decisions.map(String).join('') }, { label: '编码接收样本', value: d.coded_received.slice(0, 24).map(value => value.toFixed(2)).join(' · ') }, { label: '编码硬判决', value: d.coded_hard_decisions.map(String).join('') }, { label: 'Viterbi 信息输出', value: d.decoded_information_bits.map(String).join('') }]
  return <div className="stage10-bits" aria-label="信号链比特序列预览">{rows.map(row => <div className="stage10-bit-row" key={row.label}><strong>{row.label}</strong><code>{row.value || '—'}</code></div>)}<p className="stage10-note">接收样本只列出前 24 个数值；硬判决规则为样本大于 0 判为 1。</p></div>
}
