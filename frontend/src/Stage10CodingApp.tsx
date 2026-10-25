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

export default function Stage10CodingApp() {
  const [count, setCount] = useState('256')
  const [snr, setSnr] = useState('4')
  const [seed, setSeed] = useState('2026')
  const [details, setDetails] = useState(false)
  const [experiment, setExperiment] = useState<Experiment | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

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

function BitsPanel({ experiment }: { experiment: Experiment }) {
  const d = experiment.details
  const rows = [{ label: '信息位', value: d.information_bits.map(String).join('') }, { label: '编码码字', value: d.encoded_bits.map(String).join('') }, { label: '未编码接收样本', value: d.uncoded_received.slice(0, 24).map(value => value.toFixed(2)).join(' · ') }, { label: '未编码硬判决', value: d.uncoded_hard_decisions.map(String).join('') }, { label: '编码接收样本', value: d.coded_received.slice(0, 24).map(value => value.toFixed(2)).join(' · ') }, { label: '编码硬判决', value: d.coded_hard_decisions.map(String).join('') }, { label: 'Viterbi 信息输出', value: d.decoded_information_bits.map(String).join('') }]
  return <div className="stage10-bits" aria-label="信号链比特序列预览">{rows.map(row => <div className="stage10-bit-row" key={row.label}><strong>{row.label}</strong><code>{row.value || '—'}</code></div>)}<p className="stage10-note">接收样本只列出前 24 个数值；硬判决规则为样本大于 0 判为 1。</p></div>
}
