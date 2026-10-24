import { useState } from 'react'
import './App.css'
import './TimingSynchronization.css'
import { apiRequest, apiUrl } from './api'
import { ChartFrame, MetricGrid } from './DataViz'
import { formatBer } from './dataVizUtils'

const API = apiUrl('/api/stage08/challenges')
type Waveform = { sample_indices: number[]; time_symbols: number[]; transmit: number[]; receive: number[]; matched_filter: number[]; group_delay_samples: number; pilot_start_symbol: number; payload_start_symbol: number }
type Challenge = { challenge_id: string; status: string; mode: 'guided' | 'challenge'; objective: string; parameters: { samples_per_symbol: number; rolloff: number; span_symbols: number; timing_offset_unit: string; symbol_time_unit: string; eb_n0_db: number; n_payload_symbols: number; pilot_symbols: number; pilot_bits: number[] }; waveform: Waveform }
type Score = { phase_samples: number; mse: number }
type Measurement = { status: string; timing_offset_hat_samples: number; timing_offset_hat_symbols: number; unit: string; method: string; pilot_symbols_used: number; candidate_scores: Score[] }
type Ber = { phase_samples: number; n_errors: number; n_compared: number; ber: number; payload_symbol_start: number; payload_symbol_end_exclusive: number }
type Compensation = { status: string; before: Ber; after: Ber; improved: boolean }
type Feedback = { actual_fault: { type: string; timing_offset_samples: number; timing_offset_symbols: number }; seed: number; measurement: { estimate_samples: number; error_samples: number; candidate_scores: Score[] }; compensation: Compensation; effective_payload: { n_compared: number; symbol_start: number; symbol_end_exclusive: number }; lesson: { model: string; estimator: string; compensation: string; filtering: string; conclusion: string; limitations: string } }

export default function TimingSynchronizationApp() {
  const [mode, setMode] = useState<'guided' | 'challenge'>('challenge')
  const [offset, setOffset] = useState('3')
  const [snr, setSnr] = useState('8')
  const [seed, setSeed] = useState('2026')
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [measurement, setMeasurement] = useState<Measurement | null>(null)
  const [fault, setFault] = useState<'timing_offset' | 'no_timing_offset'>('timing_offset')
  const [diagnosisCorrect, setDiagnosisCorrect] = useState(false)
  const [diagnosisMessage, setDiagnosisMessage] = useState('')
  const [compensationPhase, setCompensationPhase] = useState('0')
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
    const body = mode === 'guided'
      ? { mode, timing_offset_samples: Number(offset), eb_n0_db: Number(snr), n_payload_symbols: 1024, seed: Number(seed) }
      : { mode, eb_n0_db: Number(snr), n_payload_symbols: 1024 }
    const next = await apiRequest<Challenge>(API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    setChallenge(next); setMeasurement(null); setDiagnosisCorrect(false); setDiagnosisMessage(''); setCompensation(null); setFeedback(null); setCompensationPhase('0')
  })

  const measure = () => challenge && action(async () => {
    const result = await apiRequest<Measurement>(`${API}/${challenge.challenge_id}/measurement`)
    setMeasurement(result); setCompensationPhase(String(result.timing_offset_hat_samples))
  })

  const diagnose = () => challenge && action(async () => {
    const result = await apiRequest<{ correct: boolean; message: string }>(`${API}/diagnosis`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ challenge_id: challenge.challenge_id, suspected_fault: fault }) })
    setDiagnosisCorrect(result.correct); setDiagnosisMessage(result.message)
  })

  const compensate = () => challenge && action(async () => {
    const phase = Number(compensationPhase)
    if (!Number.isInteger(phase) || phase < -7 || phase > 7) throw new Error('采样相位必须是 -7 至 +7 的整数 samples。')
    const result = await apiRequest<Compensation>(`${API}/compensate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ challenge_id: challenge.challenge_id, compensation_samples: phase }) })
    setCompensation(result)
    setFeedback(await apiRequest<Feedback>(`${API}/${challenge.challenge_id}/feedback`))
  })

  return <div className="app">
    <header className="header timing-header"><p className="timing-eyebrow">SYMBOL TIMING / 08</p><h1>符号定时与采样同步实验室</h1><p className="subtitle">在过采样脉冲中定位符号中心，观察错误采样时刻如何影响判决</p></header>
    <main className="container timing-container">
      <section className="timing-intro"><div><span className="timing-kicker">RRC · 16 samples/symbol</span><h2>先观察，再决定采样相位</h2><p>{challenge?.objective ?? '固定 RRC 成形与匹配滤波。训练序列帮助估计静态定时偏移；你将选择采样位置，并在相同接收数据上比较 BER。'}</p></div>
        <div className="timing-create-controls"><label>实验模式<select value={mode} onChange={e => setMode(e.target.value as 'guided' | 'challenge')}><option value="challenge">隐藏挑战</option><option value="guided">引导实验</option></select></label>
          {mode === 'guided' && <label>注入延迟 <small>samples（正值表示延迟）</small><select value={offset} onChange={e => setOffset(e.target.value)}>{Array.from({ length: 15 }, (_, i) => i - 7).map(value => <option key={value} value={value}>{value > 0 ? `+${value}` : value}</option>)}</select></label>}
          <label>Eb/N₀ <small>dB</small><input type="number" min="0" max="12" step="1" value={snr} onChange={e => setSnr(e.target.value)} /></label>
          {mode === 'guided' && <label>随机种子<input type="number" min="0" max="4294967295" value={seed} onChange={e => setSeed(e.target.value)} /></label>}
          <button className="timing-primary" onClick={start} disabled={busy}>{busy ? '正在生成…' : challenge ? '创建新实验' : '创建实验'}</button>
        </div>
      </section>
      <div className="timing-parameter-strip" aria-label="固定信号参数"><span>S = 16 samples/symbol</span><span>RRC α = 0.35</span><span>跨度 = 8 Ts</span><span>两级群延迟 = 128 samples</span></div>
      {error && <div className="timing-error" role="alert">{error}</div>}
      {!challenge && <section className="timing-empty"><span>01 — CREATE</span><h2>等待实验创建</h2><p>隐藏挑战会在完成反馈前隐藏真实偏移和内部随机种子。引导实验允许设置偏移并按 seed 重放。</p></section>}
      {challenge && <>
        <section className="timing-panel"><div className="timing-panel-heading"><div><span className="timing-kicker">01 / OBSERVE</span><h2>发送脉冲与接收过采样波形</h2></div><span className="timing-badge">Eb/N₀ {challenge.parameters.eb_n0_db} dB · {challenge.parameters.n_payload_symbols} payload symbols</span></div>
          <MetricGrid className="timing-metrics" items={[{ label: '过采样率', value: `${challenge.parameters.samples_per_symbol}×`, hint: '每符号采样数' }, { label: 'RRC 滚降', value: challenge.parameters.rolloff, hint: '固定参数' }, { label: '匹配滤波延迟', value: `${challenge.waveform.group_delay_samples} samples`, hint: 'Tx + Rx 合计' }, { label: '训练序列', value: `${challenge.parameters.pilot_symbols} symbols`, hint: '首尾各 8 个不参与估计' }]} />
          <WaveformPlot waveform={challenge.waveform} />
          <p className="timing-caption">图中时间以 Ts 为单位；匹配滤波输出带有 128 samples 的级联延迟。当前接收数据的有效 BER 区间为 payload symbol {challenge.waveform.payload_start_symbol} 至 {challenge.waveform.payload_start_symbol + challenge.parameters.n_payload_symbols - 1}，不含训练和保护符号。</p>
          <button className="timing-secondary" onClick={measure} disabled={busy}>{busy ? '正在测量…' : measurement ? '重新测量定时偏移' : '测量定时偏移'}</button>
          {measurement && <><ScorePlot scores={measurement.candidate_scores} estimate={measurement.timing_offset_hat_samples} /><MetricGrid items={[{ label: '估计相位', value: `${measurement.timing_offset_hat_samples > 0 ? '+' : ''}${measurement.timing_offset_hat_samples} samples`, hint: `${measurement.timing_offset_hat_symbols.toFixed(4)} Ts` }, { label: '评分方法', value: 'Pilot MSE', hint: `${measurement.pilot_symbols_used} 个内部训练符号` }]} /></>}
        </section>
        {measurement && <section className="timing-panel"><div className="timing-panel-heading"><div><span className="timing-kicker">02 / DIAGNOSE</span><h2>判断是否存在定时偏移</h2></div><span className={`timing-badge ${diagnosisCorrect ? 'complete' : ''}`}>{diagnosisCorrect ? '诊断正确' : '等待提交'}</span></div>
          <p>结合波形中的采样位置和候选 MSE 评分，判断接收机采样是否偏离符号中心。错误判断可根据证据修改后重试。</p>
          <div className="timing-options"><label><input type="radio" name="timing-fault" checked={fault === 'timing_offset'} onChange={() => setFault('timing_offset')} />存在静态定时偏移</label><label><input type="radio" name="timing-fault" checked={fault === 'no_timing_offset'} onChange={() => setFault('no_timing_offset')} />未发现定时偏移</label><button className="timing-secondary" onClick={diagnose} disabled={busy || diagnosisCorrect}>{busy ? '处理中…' : '提交诊断'}</button></div>
          {diagnosisMessage && <p className={`timing-message ${diagnosisCorrect ? 'good' : ''}`} role="status">{diagnosisMessage}</p>}
        </section>}
        {diagnosisCorrect && measurement && <section className="timing-panel"><div className="timing-panel-heading"><div><span className="timing-kicker">03 / COMPENSATE</span><h2>选择采样相位并比较 BER</h2></div><span className="timing-badge">补偿只改变采样索引</span></div>
          <p>相位 q<sub>c</sub> 以 samples 为单位，取值 -7 到 +7。估计值是一个可尝试的采样位置；噪声下它可能偏离实际最佳值。</p>
          <div className="timing-phase-row"><label htmlFor="timing-compensation">补偿采样相位 q<sub>c</sub> <small>samples（Ts/16 网格）</small></label><input id="timing-compensation" type="range" min="-7" max="7" step="1" value={compensationPhase} onChange={e => setCompensationPhase(e.target.value)} /><output htmlFor="timing-compensation">{Number(compensationPhase) > 0 ? '+' : ''}{compensationPhase}</output><button className="timing-primary" onClick={compensate} disabled={busy}>{busy ? '正在计算…' : compensation ? '重新比较此相位' : '应用采样相位'}</button></div>
          {compensation && <><BerPlot before={compensation.before.ber} after={compensation.after.ber} /><MetricGrid items={[{ label: '补偿前 BER', value: formatBer(compensation.before.ber), hint: `${compensation.before.n_errors} / ${compensation.before.n_compared} errors` }, { label: '补偿后 BER', value: formatBer(compensation.after.ber), hint: `${compensation.after.n_errors} / ${compensation.after.n_compared} errors` }, { label: '本次结果', value: compensation.improved ? '误码减少' : '未减少', hint: '同一接收数组与 payload 索引' }]} /></>}
        </section>}
        {feedback && <section className="timing-panel timing-review"><div className="timing-panel-heading"><div><span className="timing-kicker">04 / REVIEW</span><h2>实验教学复盘</h2></div><span className="timing-badge complete">已完成</span></div>
          <MetricGrid items={[{ label: '实际定时偏移', value: `${feedback.actual_fault.timing_offset_samples > 0 ? '+' : ''}${feedback.actual_fault.timing_offset_samples} samples`, hint: `${feedback.actual_fault.timing_offset_symbols.toFixed(4)} Ts` }, { label: '估计误差', value: `${feedback.measurement.error_samples > 0 ? '+' : ''}${feedback.measurement.error_samples} samples`, hint: '估计值 − 实际值' }, { label: '补偿前误码', value: feedback.compensation.before.n_errors, hint: `${feedback.compensation.before.n_compared} 个有效 payload symbols` }, { label: '补偿后误码', value: feedback.compensation.after.n_errors, hint: `采样相位 ${feedback.compensation.after.phase_samples} samples` }]} />
          <div className="timing-lesson"><h3>信号模型</h3><p>{feedback.lesson.model}</p><h3>训练序列如何定位相位</h3><p>{feedback.lesson.estimator}</p><h3>补偿与配对 BER</h3><p>{feedback.lesson.compensation}</p><p>{feedback.lesson.filtering}</p><h3>本轮结果</h3><p>{feedback.lesson.conclusion}</p><h3>适用范围</h3><p>{feedback.lesson.limitations}</p></div>
        </section>}
      </>}
    </main>
  </div>
}

function WaveformPlot({ waveform }: { waveform: Waveform }) {
  const series = [waveform.transmit, waveform.receive, waveform.matched_filter]
  const max = Math.max(1, ...series.flat().map(Math.abs))
  const path = (values: number[]) => values.map((value, index) => `${index ? 'L' : 'M'} ${20 + index * 560 / Math.max(values.length - 1, 1)} ${90 - value / max * 68}`).join(' ')
  return <ChartFrame title="发送、接收与匹配滤波器输出" description="竖向虚线标示名义符号采样位置；波形和采样索引来自当前 API 实验数据。" xLabel="时间（Ts）" yLabel="归一化幅度" legend={[{ label: '发送 RRC', color: '#38bdf8', marker: 'line' }, { label: '接收波形', color: '#e9a568', marker: 'line' }, { label: '匹配滤波输出', color: '#6ee7b7', marker: 'line' }]} className="timing-chart"><svg viewBox="0 0 600 190" role="img" aria-label="本轮发送和接收过采样波形"><line x1="20" y1="90" x2="580" y2="90" stroke="#344256" />{waveform.matched_filter.map((_, index) => index % 16 === 0 && <line key={index} x1={20 + index * 560 / Math.max(waveform.matched_filter.length - 1, 1)} y1="15" x2={20 + index * 560 / Math.max(waveform.matched_filter.length - 1, 1)} y2="165" stroke="#6b7280" strokeDasharray="3 5" opacity=".28" />)}<path d={path(waveform.transmit)} fill="none" stroke="#38bdf8" strokeWidth="1.5" /><path d={path(waveform.receive)} fill="none" stroke="#e9a568" strokeWidth="1.35" /><path d={path(waveform.matched_filter)} fill="none" stroke="#6ee7b7" strokeWidth="2" />{waveform.matched_filter.map((value, index) => index % 16 === 0 && <circle key={`p${index}`} cx={20 + index * 560 / Math.max(waveform.matched_filter.length - 1, 1)} cy={90 - value / max * 68} r="2.4" fill="#fff" />)}</svg></ChartFrame>
}

function ScorePlot({ scores, estimate }: { scores: Score[]; estimate: number }) {
  const max = Math.max(...scores.map(point => point.mse), 1e-12)
  const path = scores.map((point, index) => `${index ? 'L' : 'M'} ${35 + index * 530 / Math.max(scores.length - 1, 1)} ${155 - point.mse / max * 125}`).join(' ')
  return <ChartFrame title="候选采样相位评分" description="越低表示该相位下训练符号样本与已知 BPSK 符号的均方误差越小。" xLabel="候选相位（samples）" yLabel="Pilot MSE" legend={[{ label: '候选 MSE', color: '#38bdf8', marker: 'line' }, { label: '估计相位', color: '#e9a568' }]} className="timing-chart"><svg viewBox="0 0 600 190" role="img" aria-label="十五个整数采样相位的 pilot 均方误差"><line x1="25" y1="160" x2="580" y2="160" stroke="#344256" /><path d={path} fill="none" stroke="#38bdf8" strokeWidth="2" />{scores.map((point, index) => <g key={point.phase_samples}><circle cx={35 + index * 530 / Math.max(scores.length - 1, 1)} cy={155 - point.mse / max * 125} r={point.phase_samples === estimate ? 6 : 4} fill={point.phase_samples === estimate ? '#e9a568' : '#38bdf8'} /><text x={35 + index * 530 / Math.max(scores.length - 1, 1)} y="179" textAnchor="middle" fill="#9ca3af" fontSize="10">{point.phase_samples}</text></g>)}</svg></ChartFrame>
}

function BerPlot({ before, after }: { before: number; after: number }) {
  const max = Math.max(before, after, 0.001)
  return <ChartFrame title="补偿前后 BER" xLabel="本轮配对统计" yLabel="误码率" legend={[{ label: '补偿前', color: '#e9a568' }, { label: '补偿后', color: '#6ee7b7' }]} className="timing-chart"><svg viewBox="0 0 600 170" role="img" aria-label={`补偿前 BER ${before}，补偿后 BER ${after}`}><line x1="20" y1="140" x2="580" y2="140" stroke="#344256" /><rect x="160" y={25 + (1 - before / max) * 90} width="90" height={Math.max(1, before / max * 90)} rx="6" fill="#e9a568" /><rect x="350" y={25 + (1 - after / max) * 90} width="90" height={Math.max(1, after / max * 90)} rx="6" fill="#6ee7b7" /><text x="205" y="160" textAnchor="middle" fill="#d1d5db" fontSize="13">补偿前</text><text x="395" y="160" textAnchor="middle" fill="#d1d5db" fontSize="13">补偿后</text><text x="205" y="20" textAnchor="middle" fill="#d1d5db" fontSize="12">{formatBer(before)}</text><text x="395" y="20" textAnchor="middle" fill="#d1d5db" fontSize="12">{formatBer(after)}</text></svg></ChartFrame>
}
