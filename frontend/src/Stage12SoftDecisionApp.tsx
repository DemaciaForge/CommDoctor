import { useState } from 'react'
import { ChartFrame, MetricGrid } from './DataViz'
import { apiRequest } from './api'
import './Stage12SoftDecision.css'

type Measure = { errors: number; compared: number; ber: number; tail_counted?: boolean; path_metric?: number; metric_scale?: number }
type Compare = {
  parameters: { n_information_bits: number; eb_n0_db: number; seed: number; include_details: boolean }
  code: { constraint_length: number; generators_octal: number[]; rate: number; tail_bits: number[]; decoder: string }
  energy: { coded_amplitude: number; coded_symbol_energy: number; noise_variance: number; noise_std: number }
  lengths: { information_bits: number; tail_bits: number; encoded_bits: number; decoded_information_bits: number }
  fairness: { same_received_samples: boolean; received_samples_sha256: string; hard_input_sha256: string; soft_input_sha256: string; noise_draws: number }
  results: { hard_decision: Measure; soft_decision: Measure; outputs_equal: boolean; decoded_tail_bits: number[] }
  teaching: { fairness: string; observation: string; limitation: string }
  details?: { information_bits: number[]; encoded_bits: number[]; received_samples: number[]; hard_decision_bits: number[]; hard_information_bits: number[]; soft_information_bits: number[] }
}
type Point = { eb_n0_db: number; seed: number; noise_variance: number; received_samples_sha256: string; hard_input_sha256: string; soft_input_sha256: string; hard_decision: Measure; soft_decision: Measure; outputs_equal: boolean }
type Sweep = { parameters: { start_db: number; stop_db: number; step_db: number; n_information_bits: number; seed: number; point_count: number; total_information_bits: number }; fairness: { same_payload_across_points: boolean; same_received_samples_per_point: boolean; noise_draws_per_point: number }; sampling: { zero_error_note: string }; points: Point[] }

const formatBer = (value: number) => value === 0 ? '0' : value.toPrecision(4)
const errorText = (error: unknown) => error instanceof Error ? error.message : '实验服务暂不可用，请稍后重试。'

export default function Stage12SoftDecisionApp() {
  const [count, setCount] = useState('256')
  const [snr, setSnr] = useState('4')
  const [seed, setSeed] = useState('2026')
  const [details, setDetails] = useState(true)
  const [experiment, setExperiment] = useState<Compare | null>(null)
  const [experimentBusy, setExperimentBusy] = useState(false)
  const [experimentError, setExperimentError] = useState('')
  const [start, setStart] = useState('0')
  const [stop, setStop] = useState('10')
  const [step, setStep] = useState('2')
  const [sweepCount, setSweepCount] = useState('512')
  const [sweepSeed, setSweepSeed] = useState('2026')
  const [sweep, setSweep] = useState<Sweep | null>(null)
  const [sweepBusy, setSweepBusy] = useState(false)
  const [sweepError, setSweepError] = useState('')

  const clearExperiment = <T,>(setter: (value: T) => void, value: T) => { setter(value); setExperiment(null); setExperimentError('') }
  const clearSweep = <T,>(setter: (value: T) => void, value: T) => { setter(value); setSweep(null); setSweepError('') }

  async function runCompare() {
    setExperimentBusy(true); setExperimentError(''); setExperiment(null)
    try {
      const result = await apiRequest<Compare>('/api/stage12/compare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ n_information_bits: Number(count), eb_n0_db: Number(snr), seed: Number(seed), include_details: details }) })
      setExperiment(result)
    } catch (error) { setExperimentError(errorText(error)) } finally { setExperimentBusy(false) }
  }

  async function runSweep() {
    setSweepBusy(true); setSweepError(''); setSweep(null)
    try {
      const result = await apiRequest<Sweep>('/api/stage12/ber-sweep', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ start_db: Number(start), stop_db: Number(stop), step_db: Number(step), n_information_bits: Number(sweepCount), seed: Number(sweepSeed) }) })
      setSweep(result)
    } catch (error) { setSweepError(errorText(error)) } finally { setSweepBusy(false) }
  }

  return <main className="container stage12-container">
    <header className="stage12-hero"><div><h1>同一噪声下，比较两种 Viterbi 判决</h1><p>硬判决先量化样本，软判决保留幅度。用一组可复现的 AWGN 接收数据，观察这条信息损失如何影响译码 BER。</p></div><div className="stage12-hero-spec"><strong>K=3 · (7,5)</strong><span>R=1/2 · 两个零尾位</span><span>信息位 BER 分母 = N</span></div></header>

    <section className="stage10-intro stage12-config" aria-labelledby="stage12-compare-title"><div><h2 id="stage12-compare-title">单次配对实验</h2><p>两种译码器接收完全相同的样本数组。固定 seed 后可以重复得到同一帧和同一统计结果。</p></div><form className="stage10-controls" onSubmit={event => { event.preventDefault(); void runCompare() }}>
      <label htmlFor="stage12-count">信息位数 <small>1–4096；显示细节时最多 256</small></label><input id="stage12-count" type="number" min="1" max="4096" step="1" value={count} onChange={event => clearExperiment(setCount, event.target.value)} required />
      <label htmlFor="stage12-snr">Eb/N₀ <small>dB，−10 至 30</small></label><input id="stage12-snr" type="number" min="-10" max="30" step="0.1" value={snr} onChange={event => clearExperiment(setSnr, event.target.value)} required />
      <label htmlFor="stage12-seed">随机种子 <small>0–4294967295</small></label><input id="stage12-seed" type="number" min="0" max="4294967295" step="1" value={seed} onChange={event => clearExperiment(setSeed, event.target.value)} required />
      <label className="stage10-detail-toggle"><input type="checkbox" checked={details} onChange={event => { setDetails(event.target.checked); setExperiment(null) }} />保留有限样本细节 <small>最多 256 位</small></label>
      <button className="stage10-primary" type="submit" disabled={experimentBusy}>{experimentBusy ? '正在运行配对实验…' : experiment ? '按当前参数重新运行' : '运行单次实验'}</button>
    </form></section>
    {experimentError && <div className="stage10-error" role="alert">{experimentError}</div>}
    {experiment && <CompareResults experiment={experiment} />}

    <section className="stage10-panel stage12-sweep-controls" aria-labelledby="stage12-sweep-title"><div className="stage10-heading"><div><h2 id="stage12-sweep-title">多 Eb/N₀ 配对扫描</h2><p className="stage10-note">每个点复用同一信息帧，只生成一次噪声；最多 16 点、4096 信息位/点、总计 32768 位。</p></div></div><form className="stage10-controls" onSubmit={event => { event.preventDefault(); void runSweep() }}>
      <label htmlFor="stage12-start">起始 Eb/N₀ <small>dB</small></label><input id="stage12-start" type="number" min="-10" max="30" step="0.1" value={start} onChange={event => clearSweep(setStart, event.target.value)} required />
      <label htmlFor="stage12-stop">结束 Eb/N₀ <small>dB，须大于起点</small></label><input id="stage12-stop" type="number" min="-10" max="30" step="0.1" value={stop} onChange={event => clearSweep(setStop, event.target.value)} required />
      <label htmlFor="stage12-step">扫描步长 <small>dB，范围须整除</small></label><input id="stage12-step" type="number" min="0.1" max="40" step="0.1" value={step} onChange={event => clearSweep(setStep, event.target.value)} required />
      <label htmlFor="stage12-sweep-count">每点信息位数 <small>1–4096</small></label><input id="stage12-sweep-count" type="number" min="1" max="4096" step="1" value={sweepCount} onChange={event => clearSweep(setSweepCount, event.target.value)} required />
      <label htmlFor="stage12-sweep-seed">扫描种子 <small>0–4294967295</small></label><input id="stage12-sweep-seed" type="number" min="0" max="4294967295" step="1" value={sweepSeed} onChange={event => clearSweep(setSweepSeed, event.target.value)} required />
      <button className="stage10-primary" type="submit" disabled={sweepBusy}>{sweepBusy ? '正在计算 BER 曲线…' : sweep ? '按当前参数重新扫描' : '运行 BER 扫描'}</button>
    </form></section>
    {sweepError && <div className="stage10-error" role="alert">{sweepError}</div>}
    {sweep && <SweepResults sweep={sweep} />}
    <section className="stage10-panel stage12-method"><div className="stage10-heading"><div><h2>如何解读这组数据</h2></div><span className="stage10-badge">真实 API 样本</span></div><div className="stage12-method-grid"><p><strong>硬判决</strong><br />把每个接收样本压成 0/1，再用 Hamming 距离跑 Viterbi；样本离零点有多远的信息被丢弃。</p><p><strong>软判决</strong><br />直接用样本与候选符号的平方欧氏距离累积路径度量，保留幅度和符号信息。</p><p><strong>统计边界</strong><br />软判决在 AWGN 模型下通常更充分，但有限帧的每个点都有随机性，不保证逐点严格更优。</p></div></section>
  </main>
}

function CompareResults({ experiment }: { experiment: Compare }) {
  const hard = experiment.results.hard_decision
  const soft = experiment.results.soft_decision
  return <section className="stage10-panel stage12-results" aria-labelledby="stage12-results-title"><div className="stage10-heading"><div><h2 id="stage12-results-title">同一接收数组的结果</h2><p className="stage10-note">seed {experiment.parameters.seed} · {experiment.parameters.n_information_bits} 个信息位 · {experiment.parameters.eb_n0_db} dB</p></div><span className="stage10-badge">{experiment.results.outputs_equal ? '输出一致' : '输出有差异'}</span></div><MetricGrid items={[{ label: '硬判决 BER', value: formatBer(hard.ber), hint: `${hard.errors} / ${hard.compared} 个信息位`, tone: 'warning' }, { label: '软判决 BER', value: formatBer(soft.ber), hint: `${soft.errors} / ${soft.compared} 个信息位`, tone: 'good' }, { label: '编码帧长度', value: experiment.lengths.encoded_bits, hint: `含 ${experiment.lengths.tail_bits} 个零尾输入` }, { label: '噪声方差 σ²', value: experiment.energy.noise_variance.toPrecision(4), hint: `σ = ${experiment.energy.noise_std.toPrecision(4)}` }]} /><div className="stage12-fairness"><strong>公平性证据</strong><span>同一接收样本：{experiment.fairness.received_samples_sha256.slice(0, 16)}…</span><span>硬/软输入摘要相同：{experiment.fairness.hard_input_sha256 === experiment.fairness.soft_input_sha256 ? '是' : '否'}</span><span>噪声抽样次数：{experiment.fairness.noise_draws}</span></div><div className="stage12-observation"><p>{experiment.teaching.fairness}</p><p>{experiment.teaching.observation}</p><p>{experiment.teaching.limitation}</p></div>{experiment.details && <DetailsPreview details={experiment.details} />}</section>
}

function DetailsPreview({ details }: { details: NonNullable<Compare['details']> }) {
  const rows = [{ label: '信息位', value: details.information_bits.join('') }, { label: '编码码字', value: details.encoded_bits.join('') }, { label: '接收样本（前 24）', value: details.received_samples.slice(0, 24).map(value => value.toFixed(2)).join(' · ') }, { label: '硬判决信息输出', value: details.hard_information_bits.join('') }, { label: '软判决信息输出', value: details.soft_information_bits.join('') }]
  return <div className="stage12-details" aria-label="单次实验细节预览">{rows.map(row => <div className="stage10-bit-row" key={row.label}><strong>{row.label}</strong><code>{row.value}</code></div>)}</div>
}

function SweepResults({ sweep }: { sweep: Sweep }) {
  const zeroCount = sweep.points.reduce((count, point) => count + Number(point.soft_decision.errors === 0), 0)
  return <section className="stage10-panel stage12-results" aria-labelledby="stage12-sweep-results-title"><div className="stage10-heading"><div><h2 id="stage12-sweep-results-title">实测 BER 曲线</h2><p className="stage10-note">{sweep.parameters.point_count} 个点 · 每点 {sweep.parameters.n_information_bits} 信息位 · 根种子 {sweep.parameters.seed}</p></div><span className="stage10-badge">同一 payload / 点内同一样本</span></div><MetricGrid items={[{ label: '扫描范围', value: `${sweep.parameters.start_db}–${sweep.parameters.stop_db} dB`, hint: `步长 ${sweep.parameters.step_db} dB` }, { label: '总信息位', value: sweep.parameters.total_information_bits, hint: '所有点的统计总量' }, { label: '软判决零误码点', value: `${zeroCount} / ${sweep.points.length}`, hint: '有限样本未观察到错误' }]} /><SweepChart sweep={sweep} /><div className="stage10-table-wrap" tabIndex={0} role="region" aria-label="Stage12 BER 扫描数据表，可横向滚动查看"><table className="stage10-sweep-table stage12-table"><caption>每个 Eb/N₀ 点的实际信息误码数、分母与 BER</caption><thead><tr><th scope="col">Eb/N₀</th><th scope="col">σ²</th><th scope="col">硬判决 errors / N</th><th scope="col">硬 BER</th><th scope="col">软判决 errors / N</th><th scope="col">软 BER</th><th scope="col">同一样本</th></tr></thead><tbody>{sweep.points.map(point => <tr key={point.eb_n0_db}><th scope="row">{point.eb_n0_db} dB</th><td>{point.noise_variance.toPrecision(5)}</td><td>{point.hard_decision.errors} / {point.hard_decision.compared}</td><td>{formatBer(point.hard_decision.ber)}</td><td>{point.soft_decision.errors} / {point.soft_decision.compared}</td><td>{formatBer(point.soft_decision.ber)}</td><td>{point.hard_input_sha256 === point.soft_input_sha256 ? '是' : '否'}</td></tr>)}</tbody></table></div><p className="stage10-note">BER 始终按信息位 N 统计，两个零尾位不进入分母。0/N 是本次有限样本的真实测量值，不是对真实误码概率为零的证明。</p></section>
}

function SweepChart({ sweep }: { sweep: Sweep }) {
  const positive = sweep.points.flatMap(point => [point.hard_decision.ber, point.soft_decision.ber]).filter(value => value > 0)
  const floorExponent = Math.min(-3, positive.length ? Math.floor(Math.log10(Math.min(...positive))) - 1 : -3)
  const x = (index: number) => 48 + index * 505 / Math.max(sweep.points.length - 1, 1)
  const y = (value: number) => 22 + (-Math.log10(value)) / -floorExponent * 128
  const ticks = Array.from({ length: -floorExponent + 1 }, (_, index) => 10 ** -index)
  const series: { key: 'hard_decision' | 'soft_decision'; label: string; color: string }[] = [{ key: 'hard_decision', label: '硬判决', color: '#e9a568' }, { key: 'soft_decision', label: '软判决', color: '#6ee7b7' }]
  return <ChartFrame title="硬 / 软判决 BER（对数纵轴）" description="非零 BER 按实测值连线；零误码点在下沿单独标记，表格保留精确 0/N。" xLabel="Eb/N₀（dB）" yLabel="BER" legend={series.map(item => ({ label: item.label, color: item.color, marker: 'line' }))} className="stage12-chart"><svg viewBox="0 0 600 220" role="img" aria-label="硬判决和软判决的实测 BER 曲线">{ticks.map(value => <g key={value}><line x1="40" y1={y(value)} x2="568" y2={y(value)} stroke="#344256" strokeDasharray="3 4" /><text x="35" y={y(value) + 4} textAnchor="end" fill="#cbd5e1" fontSize="10">{formatBer(value)}</text></g>)}{series.map(({ key, color, label }) => { const path = sweep.points.map((point, index) => point[key].ber > 0 ? `${index === 0 || sweep.points[index - 1][key].ber === 0 ? 'M' : 'L'} ${x(index)} ${y(point[key].ber)}` : '').filter(Boolean).join(' '); return <g key={key} aria-label={label}><path d={path} fill="none" stroke={color} strokeWidth="2.2" />{sweep.points.map((point, index) => point[key].ber === 0 ? <path key={point.eb_n0_db} d={`M ${x(index) - 5} 167 L ${x(index) + 5} 167 L ${x(index)} 158 Z`} fill="none" stroke={color} strokeWidth="1.8"><title>{label}: 0 errors / {point[key].compared}</title></path> : <circle key={point.eb_n0_db} cx={x(index)} cy={y(point[key].ber)} r="4" fill={color}><title>{label}: {point[key].errors} / {point[key].compared}, BER {point[key].ber}</title></circle>)}</g>})}{sweep.points.map((point, index) => <text key={point.eb_n0_db} x={x(index)} y="190" textAnchor="middle" fill="#cbd5e1" fontSize="10">{point.eb_n0_db}</text>)}</svg></ChartFrame>
}
