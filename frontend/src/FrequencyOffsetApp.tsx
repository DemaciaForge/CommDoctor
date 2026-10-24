import { useState } from 'react'
import './App.css'
import './FrequencyOffset.css'
import { apiRequest, apiUrl } from './api'
import { ChartFrame, formatBer } from './DataViz'

type Challenge = {
  challenge_id: string
  objective: string
  epsilon_unit: string
  estimator_unambiguous_range: number[]
  n_symbols: number
  eb_n0_db: number
  ber_theoretical: number
  before: { ber: number; n_errors: number }
  signal: { i: number[]; q: number[]; phase_rad: number[]; constellation: { i: number; q: number }[] }
}

type Estimate = { epsilon_hat: number; decision_deadband: number; method: string; epsilon_unit: string }
type Compensation = { before: { ber: number; n_errors: number }; after: { ber: number; n_errors: number }; improved: boolean }
type Feedback = {
  actual_fault: { type: string; epsilon: number }
  diagnosis: { suspected_fault: string; correct: boolean }
  estimate: { epsilon_hat: number; error: number }
  compensation: { epsilon_hat: number; ber: number; n_errors: number }
  ber: { theoretical: number; before: { ber: number; n_errors: number }; after: { ber: number; n_errors: number } }
  lesson: { model: string; estimator: string; compensation: string; conclusion: string; limitations: string }
}

const API = apiUrl('/api/stage04/challenges')

export default function FrequencyOffsetApp() {
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [suspectedFault, setSuspectedFault] = useState<'frequency_offset' | 'no_offset'>('frequency_offset')
  const [diagnosisCorrect, setDiagnosisCorrect] = useState(false)
  const [diagnosisMessage, setDiagnosisMessage] = useState('')
  const [epsilonInput, setEpsilonInput] = useState('0')
  const [compensation, setCompensation] = useState<Compensation | null>(null)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const action = async (work: () => Promise<void>) => {
    setBusy(true); setError('')
    try { await work() } catch (cause) { setError(cause instanceof Error ? cause.message : '操作失败，请重试') }
    finally { setBusy(false) }
  }

  const start = () => action(async () => {
    const next = await apiRequest<Challenge>(API, { method: 'POST' })
    setChallenge(next); setEstimate(null); setDiagnosisCorrect(false); setDiagnosisMessage('')
    setCompensation(null); setFeedback(null); setEpsilonInput('0')
  })

  const measure = () => challenge && action(async () => {
    const measured = await apiRequest<Estimate>(`${API}/${challenge.challenge_id}/estimate`)
    setEstimate(measured)
    // Treat estimates inside the documented normal-state noise deadband as zero for compensation.
    setEpsilonInput(Math.abs(measured.epsilon_hat) <= measured.decision_deadband ? '0' : measured.epsilon_hat.toFixed(6))
  })

  const diagnose = () => challenge && action(async () => {
    const result = await apiRequest<{ correct: boolean; message: string }>(`${API}/diagnosis`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ challenge_id: challenge.challenge_id, suspected_fault: suspectedFault }),
    })
    setDiagnosisCorrect(result.correct); setDiagnosisMessage(result.message)
  })

  const compensate = () => challenge && action(async () => {
    const value = Number(epsilonInput)
    if (!epsilonInput.trim() || !Number.isFinite(value) || Math.abs(value) >= 0.25) {
      throw new Error('请输入有限的归一化频偏，范围必须严格位于 -0.25 到 +0.25 cycles/symbol 之间。')
    }
    const result = await apiRequest<Compensation>(`${API}/compensate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ challenge_id: challenge.challenge_id, epsilon_hat: value }),
    })
    setCompensation(result)
    setFeedback(await apiRequest<Feedback>(`${API}/${challenge.challenge_id}/feedback`))
  })

  return <div className="app">
    <header className="header frequency-header">
      <p className="frequency-eyebrow">CARRIER RECOVERY / 04</p>
      <h1>频率偏移诊断实验室</h1>
      <p className="subtitle">在复基带信号中识别相位旋转，并验证频偏补偿</p>
    </header>
    <main className="container frequency-container">
      <section className="frequency-intro"><div><span className="frequency-kicker">真实 BPSK 复基带实验</span><h2>载波是否正在旋转？</h2><p>{challenge?.objective ?? '生成一轮随机正常对照或频率偏移实验。查看 I/Q 波形、星座和相位轨迹，估计归一化频偏后提交诊断。频率偏移表示载波旋转速度发生变化。'}</p><p className="unit-note">ε = Δf·Tₛ，单位 cycles/symbol；未设置采样率或符号率，不换算 Hz。初始载波相位为 0。</p></div><button className="frequency-primary" onClick={start} disabled={busy}>{challenge ? '创建新实验' : '创建实验挑战'}</button></section>
      {error && <div className="frequency-error" role="alert">⚠️ {error}</div>}
      {!challenge && <section className="frequency-empty"><span>01 — CAPTURE</span><h2>等待实验创建</h2><p>每轮随机选择零频偏对照或正负频偏故障；实际偏移参数将在完成复盘后揭示。</p></section>}
      {challenge && <>
        <section className="frequency-panel">
          <div className="frequency-panel-heading"><div><span className="frequency-kicker">01 / SIGNAL</span><h2>接收信号与测量</h2></div><span className="frequency-badge">{challenge.n_symbols.toLocaleString()} symbols · Eb/N₀ {challenge.eb_n0_db} dB</span></div>
          <div className="frequency-metrics"><article><span>理论 BPSK BER</span><strong>{formatBer(challenge.ber_theoretical)}</strong><em>相干 BPSK/AWGN</em></article><article><span>当前接收 BER</span><strong>{formatBer(challenge.before.ber)}</strong><em>{challenge.before.n_errors} errors / {challenge.n_symbols.toLocaleString()} symbols</em></article></div>
          <div className="frequency-plots"><IQPlot title="复基带 I/Q 波形" i={challenge.signal.i} q={challenge.signal.q} /><ConstellationPlot points={challenge.signal.constellation} /><PhasePlot values={challenge.signal.phase_rad} /></div>
          <p className="frequency-caption">绘图数据来自本轮接收复样本；星座颜色由 I/Q 位置着色。估计器无歧义范围为 |ε| &lt; 0.25 cycles/symbol。</p>
          <button className="frequency-secondary" onClick={measure} disabled={busy}>{estimate ? '重新估计频偏' : '计算频偏估计'}</button>
          {estimate && <div className="frequency-estimate"><span>平方 BPSK 频谱峰值估计</span><strong>{estimate.epsilon_hat.toFixed(6)} <small>cycles/symbol</small></strong><p>{estimate.method}正常状态判别死区 ±{estimate.decision_deadband.toFixed(3)} cycles/symbol。</p></div>}
        </section>

        {estimate && <section className="frequency-panel">
          <div className="frequency-panel-heading"><div><span className="frequency-kicker">02 / DIAGNOSE</span><h2>判断频率偏移状态</h2></div><span className={`frequency-badge ${diagnosisCorrect ? 'complete' : ''}`}>{diagnosisCorrect ? '诊断正确' : '等待提交'}</span></div>
          <p>根据相位轨迹和估计值，判断载波是否存在明显频率偏移。错误判断可以继续观察并重试。</p>
          <div className="frequency-options"><label><input type="radio" name="frequency-diagnosis" checked={suspectedFault === 'frequency_offset'} onChange={() => setSuspectedFault('frequency_offset')} />存在频率偏移</label><label><input type="radio" name="frequency-diagnosis" checked={suspectedFault === 'no_offset'} onChange={() => setSuspectedFault('no_offset')} />未发现明显频偏</label><button className="frequency-secondary" onClick={diagnose} disabled={busy || diagnosisCorrect}>{busy ? '处理中…' : '提交诊断'}</button></div>
          {diagnosisMessage && <p className={`frequency-message ${diagnosisCorrect ? 'good' : ''}`} role="status">{diagnosisMessage}</p>}
        </section>}

        {diagnosisCorrect && estimate && <section className="frequency-panel">
          <div className="frequency-panel-heading"><div><span className="frequency-kicker">03 / COMPENSATE</span><h2>输入频偏估计并补偿</h2></div><span className={`frequency-badge ${compensation?.improved ? 'complete' : ''}`}>{compensation ? (compensation.improved ? '误码下降' : '真实结果已计算') : '补偿实验'}</span></div>
          <p>输入 ε̂（cycles/symbol），接收机将对原始复样本应用 exp(−j·2π·ε̂·n)，再按补偿后实部进行 BPSK 硬判决。</p>
          <div className="frequency-input-row"><label htmlFor="epsilon-hat">补偿频偏 ε̂ <small>cycles/symbol</small></label><input id="epsilon-hat" type="number" min="-0.249999" max="0.249999" step="0.000001" value={epsilonInput} onChange={event => setEpsilonInput(event.target.value)} /><button className="frequency-primary" onClick={compensate} disabled={busy}>{busy ? '正在补偿…' : compensation ? '再次测试补偿值' : '执行补偿'}</button></div>
          {compensation && <div className="frequency-metrics"><article><span>补偿前 BER</span><strong>{formatBer(compensation.before.ber)}</strong><em>{compensation.before.n_errors} errors</em></article><article><span>补偿后 BER</span><strong>{formatBer(compensation.after.ber)}</strong><em>{compensation.after.n_errors} errors</em></article><article><span>实际比较</span><strong>{compensation.improved ? '误码减少' : '没有减少'}</strong><em>由同一组样本重新判决</em></article></div>}
        </section>}

        {feedback && <section className="frequency-panel frequency-review">
          <div className="frequency-panel-heading"><div><span className="frequency-kicker">04 / REVIEW</span><h2>实验教学复盘</h2></div><span className="frequency-badge complete">已完成</span></div>
          <div className="frequency-answer"><span>实际状态</span><strong>{feedback.actual_fault.type === 'none' ? '正常对照 · ε = 0' : `频率偏移 · ε = ${feedback.actual_fault.epsilon > 0 ? '+' : ''}${feedback.actual_fault.epsilon.toFixed(4)}`}</strong><span>诊断：{feedback.diagnosis.correct ? '正确' : '错误'}</span></div>
          <div className="frequency-metrics"><article><span>频偏估计 ε̂</span><strong>{feedback.estimate.epsilon_hat.toFixed(6)}</strong><em>cycles/symbol</em></article><article><span>估计误差 ε̂ − ε</span><strong>{feedback.estimate.error > 0 ? '+' : ''}{feedback.estimate.error.toFixed(6)}</strong><em>cycles/symbol</em></article><article><span>实际补偿值</span><strong>{feedback.compensation.epsilon_hat.toFixed(6)}</strong><em>cycles/symbol</em></article><article><span>补偿前 BER</span><strong>{formatBer(feedback.ber.before.ber)}</strong><em>{feedback.ber.before.n_errors} errors</em></article><article><span>补偿后 BER</span><strong>{formatBer(feedback.ber.after.ber)}</strong><em>{feedback.ber.after.n_errors} errors</em></article><article><span>理论 BER</span><strong>{formatBer(feedback.ber.theoretical)}</strong><em>相干 BPSK/AWGN</em></article></div>
          <div className="frequency-lesson"><h3>信号模型</h3><p>{feedback.lesson.model}</p><h3>频偏估计</h3><p>{feedback.lesson.estimator}</p><h3>补偿机理</h3><p>{feedback.lesson.compensation}</p><h3>本轮结论</h3><p>{feedback.lesson.conclusion}</p><h3>适用范围与局限</h3><p>{feedback.lesson.limitations}</p></div>
        </section>}
      </>}
    </main>
  </div>
}

function IQPlot({ title, i, q }: { title: string; i: number[]; q: number[] }) {
  const max = Math.max(1.5, ...i.map(Math.abs), ...q.map(Math.abs))
  return <ChartFrame title={title} xLabel="符号序号" yLabel="幅度" legend={[{ label: 'I（实部）', color: '#38bdf8' }, { label: 'Q（虚部）', color: '#e9a568' }]} className="frequency-plot"><svg viewBox="0 0 600 190" role="img" aria-label={title}><line x1="25" y1="95" x2="590" y2="95" stroke="#344256" />{i.map((v, index) => <g key={index}><circle cx={28 + index * 1.1} cy={95 - v / max * 70} r="1.8" fill="#38bdf8" /><circle cx={28 + index * 1.1} cy={95 - q[index] / max * 70} r="1.8" fill="#e9a568" /></g>)}</svg></ChartFrame>
}

function ConstellationPlot({ points }: { points: { i: number; q: number }[] }) {
  return <ChartFrame title="复基带星座图" xLabel="I（同相）" yLabel="Q（正交）" legend={[{ label: 'I ≥ 0', color: '#6ee7b7' }, { label: 'I < 0', color: '#e9a568' }]} className="frequency-plot"><svg viewBox="0 0 240 190" role="img" aria-label="复基带星座图"><line x1="10" y1="95" x2="230" y2="95" stroke="#344256"/><line x1="120" y1="8" x2="120" y2="182" stroke="#344256"/>{points.map((point, index) => <circle key={index} cx={120 + point.i * 48} cy={95 - point.q * 48} r="2" fill={point.i >= 0 ? '#6ee7b7' : '#e9a568'} opacity=".72" />)}</svg></ChartFrame>
}

function PhasePlot({ values }: { values: number[] }) {
  const min = Math.min(...values, -0.2); const max = Math.max(...values, 0.2); const span = Math.max(max - min, 0.01)
  const path = values.map((v, index) => `${index ? 'L' : 'M'} ${20 + index * (560 / Math.max(values.length - 1, 1))} ${170 - (v - min) / span * 145}`).join(' ')
  return <ChartFrame title="平方信号解调后的相位轨迹" xLabel="抽样序号（每 8 符号）" yLabel="相位（rad）" legend={[{ label: '相位轨迹', color: '#6ee7b7', marker: 'line' }]} className="frequency-plot phase-plot"><svg viewBox="0 0 600 190" role="img" aria-label="相位轨迹"><line x1="15" y1="170" x2="590" y2="170" stroke="#344256"/><path d={path} fill="none" stroke="#6ee7b7" strokeWidth="2"/></svg></ChartFrame>
}
