import { useState } from 'react'
import './App.css'
import './FaultDiagnosis.css'
import './DiagnosticChallenge.css'
import { apiRequest, apiUrl } from './api'
import { ChartFrame, formatBer } from './DataViz'

type Challenge = {
  challenge_id: string
  status: string
  objective: string
  eb_n0_db: number
  n_bits: number
  ber_theoretical: number
  normal: { ber: number; n_errors: number; threshold: number }
  with_fault: { ber: number; n_errors: number; threshold: number }
  samples: { tx_symbols: number[]; rx_normal: number[]; rx_with_fault: number[] }
}

type Measurement = {
  rx_mean: number
  std_error: number
  threshold_3sigma: number
  n_samples: number
  noise_std: number
}

type Repair = {
  before: { ber: number; n_errors: number; threshold: number }
  after: { ber: number; n_errors: number; threshold: number }
  improved: boolean
}

type Feedback = {
  actual_fault: { type: string; dc_offset: number }
  diagnosis_correct: boolean
  evidence: { rx_mean: number; std_error: number; threshold_3sigma: number; n_samples: number }
  noise_std: number
  repair: Repair & { ideal_threshold_result: { ber: number; n_errors: number; threshold: number } }
  explanation: { fault_mechanism: string; repair_mechanism: string; coaching: string }
}

const API = apiUrl('/api/challenges')

function DiagnosticChallengeApp() {
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [measurement, setMeasurement] = useState<Measurement | null>(null)
  const [diagnosisMessage, setDiagnosisMessage] = useState('')
  const [diagnosisCorrect, setDiagnosisCorrect] = useState(false)
  const [diagnosis, setDiagnosis] = useState<'dc_offset' | 'no_fault'>('dc_offset')
  const [threshold, setThreshold] = useState(0)
  const [repair, setRepair] = useState<Repair | null>(null)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const run = async (action: () => Promise<void>) => {
    setLoading(true)
    setError('')
    try { await action() } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败，请重试')
    } finally { setLoading(false) }
  }

  const startChallenge = () => run(async () => {
    const next = await apiRequest<Challenge>(API, { method: 'POST' })
    setChallenge(next)
    setMeasurement(null)
    setDiagnosisMessage('')
    setDiagnosisCorrect(false)
    setRepair(null)
    setFeedback(null)
  })

  const collectMeasurement = () => challenge && run(async () => {
    const evidence = await apiRequest<Measurement>(`${API}/${challenge.challenge_id}/measurement`)
    setMeasurement(evidence)
    setThreshold(Number(evidence.rx_mean.toFixed(2)))
  })

  const submitDiagnosis = () => challenge && run(async () => {
    const result = await apiRequest<{ correct: boolean; message: string }>(`${API}/diagnosis`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ challenge_id: challenge.challenge_id, suspected_fault: diagnosis }),
    })
    setDiagnosisCorrect(result.correct)
    setDiagnosisMessage(result.message)
  })

  const runRepair = () => challenge && run(async () => {
    const result = await apiRequest<Repair>(`${API}/repair`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ challenge_id: challenge.challenge_id, threshold }),
    })
    setRepair(result)
    const report = await apiRequest<Feedback>(`${API}/${challenge.challenge_id}/feedback`)
    setFeedback(report)
  })

  return (
    <div className="app">
      <header className="header">
        <p className="challenge-eyebrow">FIELD LAB / 03</p>
        <h1>诊断挑战</h1>
        <p className="subtitle">从真实信号证据出发，判断故障并验证修复</p>
      </header>
      <main className="container fault-diagnosis-container challenge-container">
        <section className="challenge-intro">
          <div><span className="challenge-kicker">交互式实验 · DC 偏移</span><h2>找出接收机里的异常</h2>
            <p>{challenge?.objective ?? '启动一轮随机生成的 BPSK/AWGN 通信实验。BER（误码率）表示错误比特占全部比特的比例；故障参数由实验服务保管。先观察波形，再收集测量证据并提交诊断。'}</p>
          </div>
          <button className="challenge-primary" onClick={startChallenge} disabled={loading}>{challenge ? '重新开始挑战' : '开始挑战'}</button>
        </section>

        {error && <div className="error-message" role="alert">⚠️ {error}</div>}
        {!challenge && <section className="challenge-empty"><span>01 — OBSERVE</span><h2>等待实验启动</h2><p>开始后会生成新的随机实验。先观察接收信号与误码表现，不要急着猜答案。</p></section>}
        {challenge && <>
          <section className="challenge-section">
            <div className="challenge-section-head"><div><span className="challenge-kicker">01 / OBSERVE</span><h2>观察通信实验</h2></div><span className="challenge-chip">Eb/N₀ {challenge.eb_n0_db} dB · {challenge.n_bits.toLocaleString()} bits</span></div>
            <div className="challenge-metrics">
              <article><span>理论 BER</span><strong>{formatBer(challenge.ber_theoretical, 3)}</strong><em>相干 BPSK/AWGN</em></article>
              <article><span>基准误码</span><strong>{challenge.normal.n_errors} <small>/ {challenge.n_bits}</small></strong><em>无故障接收</em></article>
              <article><span>当前误码</span><strong>{challenge.with_fault.n_errors} <small>/ {challenge.n_bits}</small></strong><em>实验接收结果</em></article>
            </div>
            <div className="challenge-chart-grid">
              <SignalPlot title="正常接收（基准）" samples={challenge.samples.rx_normal} symbols={challenge.samples.tx_symbols} />
              <SignalPlot title="本次实验接收" samples={challenge.samples.rx_with_fault} symbols={challenge.samples.tx_symbols} />
            </div>
            <p className="challenge-note">每个点是仿真产生的接收符号，颜色区分发送的 +1 / −1。两图来自同一批发送比特与噪声。</p>
          </section>

          <section className="challenge-section">
            <div className="challenge-section-head"><div><span className="challenge-kicker">02 / MEASURE</span><h2>收集测量证据</h2></div><span className={`challenge-status ${measurement ? 'is-done' : ''}`}>{measurement ? '证据已收集' : '待测量'}</span></div>
            <p>计算接收信号均值，并与均值估计的 3σ 界限比较。DC 偏移会让均值持续偏离零；测量值来自本次实际接收样本。</p>
            <button className="challenge-secondary" onClick={collectMeasurement} disabled={loading}>{measurement ? '重新测量' : '测量接收均值'}</button>
            {measurement && <div className="challenge-metrics evidence-metrics">
              <article><span>接收均值</span><strong>{measurement.rx_mean.toFixed(4)}</strong></article>
              <article><span>标准误差</span><strong>{measurement.std_error.toFixed(4)}</strong></article>
              <article><span>均值 3σ 界限</span><strong>±{measurement.threshold_3sigma.toFixed(4)}</strong><em>{measurement.n_samples.toLocaleString()} 个实测样本</em></article>
            </div>}
          </section>

          <section className="challenge-section">
            <div className="challenge-section-head"><div><span className="challenge-kicker">03 / DIAGNOSE</span><h2>提交你的判断</h2></div><span className={`challenge-status ${diagnosisCorrect ? 'is-done' : ''}`}>{diagnosisCorrect ? '诊断正确' : '等待判断'}</span></div>
            <p>结合波形、误码和测量证据，判断接收链路是否存在 DC 偏移。错误时可以继续测量并重新判断。</p>
            <div className="challenge-choice">
              <label><input type="radio" name="diagnosis" value="dc_offset" checked={diagnosis === 'dc_offset'} onChange={() => setDiagnosis('dc_offset')} />存在 DC 偏移</label>
              <label><input type="radio" name="diagnosis" value="no_fault" checked={diagnosis === 'no_fault'} onChange={() => setDiagnosis('no_fault')} />没有明显故障</label>
              <button className="challenge-secondary" onClick={submitDiagnosis} disabled={loading || !measurement || diagnosisCorrect}>{loading ? '处理中…' : '提交判断'}</button>
            </div>
            {diagnosisMessage && <p className={`challenge-feedback ${diagnosisCorrect ? 'positive' : ''}`} role="status">{diagnosisMessage}</p>}
          </section>

          {diagnosisCorrect && <section className="challenge-section">
            <div className="challenge-section-head"><div><span className="challenge-kicker">04 / REPAIR</span><h2>调整判决门限</h2></div><span className={`challenge-status ${repair?.improved ? 'is-done' : ''}`}>{repair ? (repair.improved ? 'BER 已改善' : '可继续尝试') : '修复实验'}</span></div>
            <p>滑动门限并运行同一批接收数据的重新判决。误码和 BER 由服务端计算。</p>
            <div className="challenge-threshold"><label htmlFor="challenge-threshold">判决门限 <strong>{threshold.toFixed(2)}</strong></label><input id="challenge-threshold" type="range" min="-1.5" max="1.5" step="0.01" value={threshold} onChange={e => setThreshold(Number(e.target.value))} /><button className="challenge-primary" onClick={runRepair} disabled={loading}>{loading ? '正在重新判决…' : repair ? '再次测试门限' : '运行修复实验'}</button></div>
            {repair && <div className="challenge-metrics repair-metrics"><article><span>修复前 BER</span><strong>{formatBer(repair.before.ber)}</strong><em>{repair.before.n_errors} errors</em></article><article><span>当前门限 BER</span><strong>{formatBer(repair.after.ber)}</strong><em>{repair.after.n_errors} errors · T={repair.after.threshold.toFixed(2)}</em></article><article><span>本次结果</span><strong>{repair.improved ? '误码下降' : '未改善'}</strong><em>以实际误码数比较</em></article></div>}
          </section>}

          {feedback && <section className="challenge-section challenge-result">
            <div className="challenge-section-head"><div><span className="challenge-kicker">05 / LEARN</span><h2>挑战复盘</h2></div><span className="challenge-status is-done">实验完成</span></div>
            <div className="challenge-answer"><span>实际故障</span><strong>DC 偏移 {feedback.actual_fault.dc_offset > 0 ? '+' : ''}{feedback.actual_fault.dc_offset.toFixed(2)}</strong><span>你的诊断：正确</span></div>
            <div className="challenge-review"><h3>证据支持</h3><p>接收均值 {feedback.evidence.rx_mean.toFixed(4)}；标准误差 {feedback.evidence.std_error.toFixed(4)}；均值 3σ 界限 ±{feedback.evidence.threshold_3sigma.toFixed(4)}。本轮使用 {feedback.evidence.n_samples.toLocaleString()} 个样本，噪声标准差为 {feedback.noise_std.toFixed(4)}。</p></div>
            <div className="challenge-metrics repair-metrics"><article><span>故障时 BER</span><strong>{formatBer(feedback.repair.before.ber)}</strong><em>{feedback.repair.before.n_errors} errors</em></article><article><span>你的修复 BER</span><strong>{formatBer(feedback.repair.after.ber)}</strong><em>{feedback.repair.after.n_errors} errors · T={feedback.repair.after.threshold.toFixed(2)}</em></article><article><span>测得均值门限参考</span><strong>{formatBer(feedback.repair.ideal_threshold_result.ber)}</strong><em>{feedback.repair.ideal_threshold_result.n_errors} errors · T={feedback.repair.ideal_threshold_result.threshold.toFixed(2)}</em></article></div>
            <div className="challenge-review"><h3>故障机理</h3><p>{feedback.explanation.fault_mechanism}</p><h3>修复原理</h3><p>{feedback.explanation.repair_mechanism}</p><h3>本次操作建议</h3><p>{feedback.explanation.coaching}</p></div>
          </section>}
        </>}
      </main>
    </div>
  )
}

function SignalPlot({ title, samples, symbols }: { title: string; samples: number[]; symbols: number[] }) {
  const count = Math.min(160, samples.length)
  const peak = Math.max(2.5, ...samples.slice(0, count).map(Math.abs))
  return <ChartFrame title={title} xLabel="样本序号（前 160 点）" yLabel="幅度（归一化）" legend={[{ label: '+1 符号', color: '#6EE7B7' }, { label: '−1 符号', color: '#E9A568' }]} className="challenge-plot"><svg viewBox="0 0 600 190" role="img" aria-label={`${title}波形`}>
    <line x1="0" y1="95" x2="600" y2="95" stroke="#374151" />
    <text x="6" y="15" fill="#9CA3AF" fontSize="11">+{peak.toFixed(1)}</text><text x="6" y="184" fill="#9CA3AF" fontSize="11">−{peak.toFixed(1)}</text>
    {samples.slice(0, count).map((value, i) => <circle key={i} cx={28 + (i / Math.max(count - 1, 1)) * 565} cy={95 - (value / peak) * 77} r="2.3" fill={symbols[i] > 0 ? '#6EE7B7' : '#E9A568'} opacity="0.82" />)}
  </svg></ChartFrame>
}

export default DiagnosticChallengeApp
