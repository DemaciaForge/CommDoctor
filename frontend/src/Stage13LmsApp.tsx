import { useState } from 'react'
import { ChartFrame, MetricGrid } from './DataViz'
import { apiRequest } from './api'
import './Stage13Lms.css'

type Result = {
  parameters: { seed: number; eb_n0_db: number; n_training_symbols: number; n_payload_symbols: number; mu: number; taps: number; path_delays_samples: number[]; path_gains: number[] }
  contract: { decision_delay_symbols: number; training_samples: number; evaluation_indices: number[]; same_channel_and_noise: boolean }
  training: { errors: { symbol: number; mse: number }[]; initial_mse: number; final_mse: number; converged: boolean; diverged_at: number | null; diagnosis: string; weights: number[] }
  results: { raw: { errors: number; compared: number; ber: number }; lms: { errors: number; compared: number; ber: number } }
  teaching: { observation: string; training: string; limitation: string }
}

const message = (error: unknown) => error instanceof Error ? error.message : '实验服务暂不可用，请检查后端服务。'
const ber = (value: number) => value === 0 ? '0' : value.toPrecision(4)

export default function Stage13LmsApp() {
  const [snr, setSnr] = useState('8')
  const [training, setTraining] = useState('60')
  const [payload, setPayload] = useState('512')
  const [mu, setMu] = useState('0.01')
  const [seed, setSeed] = useState('2026')
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    setBusy(true); setError(''); setResult(null)
    try {
      const response = await apiRequest<Result>('/api/stage13/experiments', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ eb_n0_db: Number(snr), n_training_symbols: Number(training), n_payload_symbols: Number(payload), mu: Number(mu), seed: Number(seed) }),
      })
      setResult(response)
    } catch (cause) { setError(message(cause)) } finally { setBusy(false) }
  }

  return <main className="container stage13-container">
    <header className="stage13-heading"><div><h1>LMS 自适应均衡</h1><p>已知 pilot 驱动系数更新；冻结训练结果后，在同一接收帧的独立 payload 上测量 BER。</p></div><div className="stage13-model"><strong>BPSK · 静态两径</strong><span>5 抽头 · 延迟 2 symbols</span><span>训练与评估分离</span></div></header>
    <section className="stage13-setup" aria-labelledby="stage13-setup-title"><div><h2 id="stage13-setup-title">实验参数</h2><p>采用 Stage09 的 RRC、16 samples/symbol 与 full-convolution 多径模型。</p></div><form className="stage10-controls" onSubmit={event => { event.preventDefault(); void run() }}>
      <label htmlFor="s13-snr">Eb/N₀ <small>0–20 dB</small></label><input id="s13-snr" type="number" min="0" max="20" step="0.1" value={snr} onChange={event => setSnr(event.target.value)} required />
      <label htmlFor="s13-training">训练更新数 <small>16–60 pilot symbols</small></label><input id="s13-training" type="number" min="16" max="60" step="1" value={training} onChange={event => setTraining(event.target.value)} required />
      <label htmlFor="s13-payload">评估 payload <small>128–4096 bits</small></label><input id="s13-payload" type="number" min="128" max="4096" step="1" value={payload} onChange={event => setPayload(event.target.value)} required />
      <label htmlFor="s13-mu">学习率 μ <small>0 &lt; μ ≤ 0.5</small></label><input id="s13-mu" type="number" min="0.00001" max="0.5" step="0.00001" value={mu} onChange={event => setMu(event.target.value)} required />
      <label htmlFor="s13-seed">随机 seed <small>0–4294967295</small></label><input id="s13-seed" type="number" min="0" max="4294967295" step="1" value={seed} onChange={event => setSeed(event.target.value)} required />
      <button className="stage10-primary" type="submit" disabled={busy}>{busy ? '正在训练并评估…' : '运行 LMS 实验'}</button>
    </form></section>
    {error && <div className="stage10-error" role="alert">{error}</div>}
    {result && <>
      <section className="stage13-results" aria-labelledby="stage13-results-title"><div className="stage10-heading"><div><h2 id="stage13-results-title">独立 payload 测量</h2><p className="stage10-note">seed {result.parameters.seed} · μ {result.parameters.mu} · 训练 {result.parameters.n_training_symbols} 次 · 评估 {result.parameters.n_payload_symbols} 位</p></div><span className="stage10-badge">{result.training.converged ? '训练数值稳定' : result.training.diagnosis.startsWith('训练发散') ? '训练发散' : '未稳定收敛'}</span></div>
        <MetricGrid items={[{ label: '均衡前 BER', value: ber(result.results.raw.ber), hint: `${result.results.raw.errors} / ${result.results.raw.compared} errors / bits`, tone: 'warning' }, { label: 'LMS 后 BER', value: ber(result.results.lms.ber), hint: `${result.results.lms.errors} / ${result.results.lms.compared} errors / bits`, tone: 'good' }, { label: '初始误差²', value: result.training.initial_mse.toPrecision(4), hint: '首个 pilot 窗口' }, { label: '末段 MSE', value: result.training.final_mse.toPrecision(4), hint: '最后 20% 训练样本' }]} />
        <p className="stage13-diagnosis" role="status">{result.training.diagnosis}</p>
      </section>
      <MseChart rows={result.training.errors} />
      <section className="stage13-review"><h2>本次数据复盘</h2><p>{result.teaching.training}</p><p>{result.teaching.observation}</p><p>{result.teaching.limitation}</p><p>训练样本数 {result.contract.training_samples} · 评估索引 {result.contract.evaluation_indices[0]}–{result.contract.evaluation_indices.at(-1)} · 同一信道与噪声：{result.contract.same_channel_and_noise ? '是' : '否'}</p></section>
    </>}
  </main>
}

function MseChart({ rows }: { rows: Result['training']['errors'] }) {
  const values = rows.map(row => row.mse)
  const max = Math.max(...values, 1e-12)
  const path = values.map((value, index) => `${index ? 'L' : 'M'} ${28 + index * 544 / Math.max(values.length - 1, 1)} ${162 - Math.min(value / max, 1) * 136}`).join(' ')
  return <ChartFrame title="LMS 训练误差平方" description="每个点为该次 pilot 更新前的 e[k]²；曲线数据来自当前 API 响应。" xLabel="训练更新序号" yLabel="误差平方" className="stage13-chart"><svg viewBox="0 0 600 185" role="img" aria-label="真实 LMS 训练误差平方曲线"><line x1="28" y1="162" x2="572" y2="162" stroke="#526171"/><line x1="28" y1="26" x2="28" y2="162" stroke="#526171"/><path d={path} fill="none" stroke="#38bdf8" strokeWidth="2"/></svg></ChartFrame>
}
