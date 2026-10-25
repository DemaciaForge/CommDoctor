import { useState } from 'react'
import './App.css'
import './MultipathEqualization.css'
import { apiRequest, apiUrl } from './api'
import { ChartFrame, MetricGrid } from './DataViz'
import { formatBer } from './dataVizUtils'

type Ber = { algorithm: string; n_errors: number; n_compared: number; ber: number; payload_symbol_start: number; payload_symbol_end_exclusive: number; sample_indices: number[]; improved_vs_raw?: boolean; equalizer_taps?: number[]; condition_number?: number; regularization?: number }
type Experiment = { experiment_id: string; mode: 'guided' | 'challenge'; objective: string; parameters: { samples_per_symbol: number; rolloff: number; span_symbols: number; eb_n0_db: number; n_payload_symbols: number; pilot_symbols: number; equalizer_taps: number; path_count: number; path_delays_samples?: number[]; path_gains?: number[] }; channel: { impulse?: number[]; path_count?: number }; layout: { group_delay_samples: number; tx_filter_delay_samples: number; rx_filter_delay_samples: number; channel_reference_delay_samples: number; payload_start_symbol: number; payload_end_symbol_exclusive: number; payload_sample_indices: number[] }; raw_ber: Ber; waveform: { sample_indices: number[]; transmit: number[]; receive: number[]; matched_filter: number[] }; pilot: { length: number; bits: number[] }; seed?: number }
type Measurement = { status: string; estimated_taps: number[]; condition_number: number; training_rows: number; training_residual_rms: number; regularization: number }
type Equalized = Ber & { status: string; training_residual_rms: number }
type Feedback = { lesson: { model: string; equalizer: string; tradeoff: string; conclusion: string; limitations: string }; results: Record<string, Equalized>; raw: Ber }

const endpoint = apiUrl('/api/stage09/experiments')
const sample = (values: number[], max = 280) => {
  const step = Math.max(1, Math.ceil(values.length / max))
  return values.filter((_, index) => index % step === 0)
}

export default function MultipathEqualizationApp() {
  const [mode, setMode] = useState<'guided' | 'challenge'>('guided')
  const [snr, setSnr] = useState('8')
  const [payload, setPayload] = useState('512')
  const [seed, setSeed] = useState('2026')
  const [experiment, setExperiment] = useState<Experiment | null>(null)
  const [measurement, setMeasurement] = useState<Measurement | null>(null)
  const [results, setResults] = useState<Record<string, Equalized>>({})
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const action = async (work: () => Promise<void>) => {
    setBusy(true); setError('')
    try { await work() } catch (cause) { setError(cause instanceof Error ? cause.message : '操作失败，请重试') }
    finally { setBusy(false) }
  }
  const create = () => action(async () => {
    const body = mode === 'guided' ? { mode, eb_n0_db: Number(snr), n_payload_symbols: Number(payload), seed: Number(seed) } : { mode, eb_n0_db: Number(snr), n_payload_symbols: Number(payload) }
    const next = await apiRequest<Experiment>(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    setExperiment(next); setMeasurement(null); setResults({}); setFeedback(null)
  })
  const estimate = () => experiment && action(async () => setMeasurement(await apiRequest<Measurement>(`${endpoint}/${experiment.experiment_id}/estimate`)))
  const equalize = (algorithm: 'zf' | 'mmse') => experiment && action(async () => {
    const next = await apiRequest<Equalized>(`${endpoint}/${experiment.experiment_id}/equalize`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ algorithm }) })
    setResults(previous => ({ ...previous, [algorithm]: next }))
    setFeedback(await apiRequest<Feedback>(`${endpoint}/${experiment.experiment_id}/feedback`))
  })

  return <div className="app">
    <header className="header multipath-header"><p className="multipath-eyebrow">MULTIPATH / ISI / 09</p><h1>多径信道与 ISI 均衡实验室</h1><p className="subtitle">让回波的因果证据先出现，再用训练序列比较 ZF 与 MMSE</p></header>
    <main className="container multipath-container">
      <section className="multipath-intro"><div><h2>从同一帧接收数据开始</h2><p>{experiment?.objective ?? '固定 RRC 过采样 BPSK 帧包含 guard、pilot 和 payload。默认直达径 + 一个符号延迟回波；所有 BER 使用同一 payload 索引。'}</p></div><div className="multipath-controls"><label>实验模式<select value={mode} onChange={event => setMode(event.target.value as 'guided' | 'challenge')}><option value="guided">引导实验（显示信道）</option><option value="challenge">隐藏挑战</option></select></label><label>Eb/N₀ <small>dB</small><input type="number" min="0" max="20" value={snr} onChange={event => setSnr(event.target.value)} /></label><label>Payload symbols<input type="number" min="128" max="4096" step="128" value={payload} onChange={event => setPayload(event.target.value)} /></label>{mode === 'guided' && <label>随机种子<input type="number" min="0" max="4294967295" value={seed} onChange={event => setSeed(event.target.value)} /></label>}<button className="multipath-primary" onClick={create} disabled={busy}>{busy ? '正在生成…' : experiment ? '创建新实验' : '创建实验'}</button></div></section>
      <div className="multipath-strip"><span>S = 16 samples/symbol</span><span>RRC α = 0.35 / span 8 Ts</span><span>短窗 = 5 taps</span><span>同一接收数组配对 BER</span></div>
      {error && <div className="multipath-error" role="alert">{error}</div>}
      {!experiment && <section className="multipath-empty"><h2>等待实验创建</h2><p>创建后先看发送、回波和匹配滤波输出，再测量 pilot，最后执行两种均衡器。</p></section>}
      {experiment && <>
        <section className="multipath-panel"><div className="multipath-heading"><div><span>OBSERVE</span><h2>发送波形、回波与匹配滤波</h2></div><span className="multipath-badge">{experiment.parameters.eb_n0_db} dB · {experiment.parameters.n_payload_symbols} payload</span></div><MetricGrid items={[{ label: '路径数', value: experiment.parameters.path_count, hint: mode === 'challenge' ? '系数在复盘前隐藏' : '归一化系数' }, { label: '初始 BER', value: formatBer(experiment.raw_ber.ber), hint: `${experiment.raw_ber.n_errors} / ${experiment.raw_ber.n_compared}` }, { label: '级联群延迟', value: `${experiment.layout.group_delay_samples} samples`, hint: 'Tx 64 + Rx 64' }, { label: '有效索引', value: experiment.layout.payload_sample_indices.length, hint: `symbol ${experiment.layout.payload_start_symbol} → ${experiment.layout.payload_end_symbol_exclusive}` }]} /><WaveformChart waveform={experiment.waveform} /><div className="multipath-observe-grid"><ImpulseChart impulse={experiment.channel.impulse ?? []} /><div className="multipath-explain"><h3>ISI 的因果证据</h3><p>默认回波延迟一个符号。匹配滤波中心样本同时含有当前符号和较早符号的回波项，因此相邻符号会改变判决幅度。</p><p>页面返回的 <code>payload_sample_indices</code> 是后端固定布局；原始、ZF、MMSE 都读取同一组索引，不用更容易的子集制造改善。</p></div></div><button className="multipath-secondary" onClick={estimate} disabled={busy}>{busy ? '正在测量…' : measurement ? '重新测量 pilot' : '用 pilot 测量信道'}</button>{measurement && <MeasurementPanel measurement={measurement} />}</section>
        {measurement && <section className="multipath-panel"><div className="multipath-heading"><div><span>EQUALIZE</span><h2>同一接收数据上的 ZF / MMSE</h2></div><span className="multipath-badge">λ = 噪声方差</span></div><p className="multipath-copy">ZF 尽量反演训练得到的 ISI；MMSE 加正则项，接受少量残余 ISI 来降低噪声放大。两项操作都不会重新生成 payload 或噪声。</p><div className="multipath-equalizer-actions"><button className="multipath-secondary" onClick={() => equalize('zf')} disabled={busy}>{busy ? '处理中…' : results.zf ? '重新运行 ZF' : '运行 ZF'}</button><button className="multipath-primary" onClick={() => equalize('mmse')} disabled={busy}>{busy ? '处理中…' : results.mmse ? '重新运行 MMSE' : '运行 MMSE'}</button></div>{Object.keys(results).length > 0 && <ResultTable raw={experiment.raw_ber} results={results} />}</section>}
        {feedback && <section className="multipath-panel multipath-review"><div className="multipath-heading"><div><span>REVIEW</span><h2>本次实验复盘</h2></div><span className="multipath-badge complete">已完成</span></div><div className="multipath-lesson"><h3>信号模型</h3><p>{feedback.lesson.model}</p><h3>均衡器怎样工作</h3><p>{feedback.lesson.equalizer}</p><h3>为什么结果可能变差</h3><p>{feedback.lesson.tradeoff}</p><h3>本轮结果</h3><p>{feedback.lesson.conclusion}</p><h3>适用边界</h3><p>{feedback.lesson.limitations}</p></div></section>}
      </>}
    </main>
  </div>
}

function WaveformChart({ waveform }: { waveform: Experiment['waveform'] }) {
  const tx = sample(waveform.transmit); const rx = sample(waveform.receive); const matched = sample(waveform.matched_filter); const max = Math.max(1, ...tx.map(Math.abs), ...rx.map(Math.abs), ...matched.map(Math.abs))
  const path = (values: number[]) => values.map((value, index) => `${index ? 'L' : 'M'} ${20 + index * 560 / Math.max(values.length - 1, 1)} ${90 - value / max * 68}`).join(' ')
  return <ChartFrame title="发送 / 接收 / 匹配滤波输出" description="接收波形包含静态路径叠加；采样点和延迟由后端布局返回。" xLabel="样本（预览）" yLabel="幅度" legend={[{ label: '发送', color: '#38bdf8', marker: 'line' }, { label: '接收', color: '#e9a568', marker: 'line' }, { label: '匹配滤波', color: '#6ee7b7', marker: 'line' }]} className="multipath-chart"><svg viewBox="0 0 600 190" role="img" aria-label="发送、接收和匹配滤波输出波形"><line x1="20" y1="90" x2="580" y2="90" stroke="#344256" /><path d={path(tx)} fill="none" stroke="#38bdf8" strokeWidth="1.5" /><path d={path(rx)} fill="none" stroke="#e9a568" strokeWidth="1.35" /><path d={path(matched)} fill="none" stroke="#6ee7b7" strokeWidth="2" /></svg></ChartFrame>
}

function ImpulseChart({ impulse }: { impulse: number[] }) {
  const max = Math.max(1, ...impulse.map(Math.abs)); return <ChartFrame title="静态信道冲激响应" description="离散路径系数已按 L2 范数归一化。" xLabel="延迟（samples）" yLabel="系数" className="multipath-chart"><svg viewBox="0 0 600 170" role="img" aria-label="静态多径信道冲激响应"><line x1="20" y1="135" x2="580" y2="135" stroke="#344256" />{impulse.map((value, index) => <g key={index}><line x1={30 + index * 550 / Math.max(impulse.length - 1, 1)} y1="135" x2={30 + index * 550 / Math.max(impulse.length - 1, 1)} y2={135 - value / max * 95} stroke="#e9a568" strokeWidth="3" /><circle cx={30 + index * 550 / Math.max(impulse.length - 1, 1)} cy={135 - value / max * 95} r="4" fill="#e9a568" /><text x={30 + index * 550 / Math.max(impulse.length - 1, 1)} y="157" textAnchor="middle" fill="#9ca3af" fontSize="10">{index}</text></g>)}</svg></ChartFrame>
}

function MeasurementPanel({ measurement }: { measurement: Measurement }) { return <div className="multipath-measurement"><MetricGrid items={[{ label: '训练行数', value: measurement.training_rows, hint: 'pilot 内部完整窗口' }, { label: '条件数', value: measurement.condition_number.toFixed(2), hint: 'XᵀX 数值诊断' }, { label: '训练残差 RMS', value: measurement.training_residual_rms.toFixed(4), hint: 'pilot 拟合误差' }, { label: 'MMSE λ', value: measurement.regularization.toFixed(4), hint: '噪声方差' }]} /><p role="status">已锁定本次实验的 matched-filter 数组、pilot 窗口和 payload 索引。估计只使用公开训练序列。</p></div> }

function ResultTable({ raw, results }: { raw: Ber; results: Record<string, Equalized> }) { return <div className="multipath-results" aria-label="均衡结果"><div className="multipath-result-row multipath-result-head"><span>算法</span><span>误码 / 有效数</span><span>BER</span><span>结果</span></div><div className="multipath-result-row"><strong>Raw</strong><span>{raw.n_errors} / {raw.n_compared}</span><span>{formatBer(raw.ber)}</span><span>原始判决</span></div>{(['zf', 'mmse'] as const).map(name => results[name] && <div className="multipath-result-row" key={name}><strong>{name.toUpperCase()}</strong><span>{results[name].n_errors} / {results[name].n_compared}</span><span>{formatBer(results[name].ber)}</span><span>{results[name].improved_vs_raw ? '误码减少' : '如实：未减少'}</span></div>)}</div> }
