import { useState } from 'react'
import './App.css'
import './Stage11Interleaving.css'
import { apiRequest } from './api'
import { ChartFrame, MetricGrid } from './DataViz'

type Stage11Result = {
  parameters: { n_information_bits: number; seed: number; rows: number; columns: number; burst_start: number; burst_length: number }
  lengths: { information_bits: number; tail_bits: number; encoded_bits: number; valid_interleaved_bits: number; transmitted_bits: number; padding_bits: number; decoded_information_bits: number }
  interleaver: { rows: number; columns: number; block_bits: number; output_sources: (number | null)[] }
  channel: { burst_start: number; burst_length: number; flipped_positions: number[]; flipped_count: number; transmission_error_count: number; transmission_error_indices: number[]; transmission_to_coded_index: Record<string, number | null> }
  results: { coded_error_indices_after_deinterleave: number[]; coded_error_count: number; decoded_information_error_indices: number[]; information_error_count: number; information_ber: number; information_ber_errors: number; information_ber_denominator: number; corrected_all_information_errors: boolean }
  details: { information_bits: number[]; encoded_bits: number[]; interleaved_bits: number[]; transmitted_bits: number[]; deinterleaved_bits: number[]; decoded_information_bits: number[] }
  teaching: { mapping: string; burst: string; conclusion: string; limitation: string }
}

const MAX_DIMENSION = 4096
const MAX_BLOCK_BITS = 1_048_576

export default function Stage11InterleavingApp() {
  const [count, setCount] = useState('64')
  const [rows, setRows] = useState('4')
  const [columns, setColumns] = useState('4')
  const [start, setStart] = useState('0')
  const [length, setLength] = useState('8')
  const [seed, setSeed] = useState('2026')
  const [result, setResult] = useState<Stage11Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = async () => {
    const n = Number(count), r = Number(rows), c = Number(columns), s = Number(start), q = Number(length), randomSeed = Number(seed)
    if (!Number.isInteger(n) || n < 1 || n > 4096) return setError('信息位数必须是 1 到 4096 之间的整数。')
    if (![r, c].every(Number.isInteger) || r < 1 || c < 1 || r > MAX_DIMENSION || c > MAX_DIMENSION || r * c > MAX_BLOCK_BITS) return setError('矩阵行列必须为正整数，单轴最多 4096，矩阵容量最多 1,048,576 位。')
    const encoded = 2 * (n + 2), transmitted = Math.ceil(encoded / (r * c)) * (r * c)
    if (![s, q, randomSeed].every(Number.isInteger) || s < 0 || q < 0 || randomSeed < 0 || randomSeed > 4294967295) return setError('突发索引、长度和随机种子必须是有效的非负整数。')
    if (q > transmitted || s > transmitted || s + q > transmitted) return setError(`突发区间必须完整位于传输帧内（长度 ${transmitted}，索引从 0 开始）。`)
    setBusy(true); setError('')
    try {
      const next = await apiRequest<Stage11Result>('/api/stage11/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ n_information_bits: n, rows: r, columns: c, burst_start: s, burst_length: q, seed: randomSeed }) })
      setResult(next)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '实验失败，请检查参数后重试。') }
    finally { setBusy(false) }
  }

  return <div className="app">
    <header className="header stage11-header"><h1>交织与突发错误实验室</h1><p className="subtitle">观察块交织如何把连续传输错误重新映射到卷积码位置</p></header>
    <main className="container stage11-container">
      <section className="stage10-intro stage11-config">
        <div><h2>配置单帧实验</h2><p>编码器添加两个零尾位。交织器按行写入、按列读取；填充位参加传输，但不计入编码错误统计或信息 BER 分母。</p></div>
        <form className="stage10-controls" onSubmit={event => { event.preventDefault(); void run() }}>
          <label htmlFor="stage11-count">信息位数 <small>1–4096</small></label><input id="stage11-count" type="number" min="1" max="4096" step="1" value={count} onChange={event => setCount(event.target.value)} required />
          <label htmlFor="stage11-rows">交织矩阵行数 <small>1–4096</small></label><input id="stage11-rows" type="number" min="1" max="4096" step="1" value={rows} onChange={event => setRows(event.target.value)} required />
          <label htmlFor="stage11-columns">交织矩阵列数 <small>1–4096</small></label><input id="stage11-columns" type="number" min="1" max="4096" step="1" value={columns} onChange={event => setColumns(event.target.value)} required />
          <label htmlFor="stage11-start">突发起点 <small>传输序列索引，从 0 开始</small></label><input id="stage11-start" type="number" min="0" step="1" value={start} onChange={event => setStart(event.target.value)} required />
          <label htmlFor="stage11-length">突发长度 <small>连续翻转位数</small></label><input id="stage11-length" type="number" min="0" step="1" value={length} onChange={event => setLength(event.target.value)} required />
          <label htmlFor="stage11-seed">信息位随机种子</label><input id="stage11-seed" type="number" min="0" max="4294967295" step="1" value={seed} onChange={event => setSeed(event.target.value)} required />
          <button className="stage10-primary" type="submit" disabled={busy}>{busy ? '正在运行实验…' : result ? '按当前参数重新运行' : '运行实验'}</button>
        </form>
      </section>
      {error && <div className="stage10-error" role="alert">{error}</div>}
      {!result && !error && <section className="stage10-empty"><h2>等待实验运行</h2><p>默认配置为 64 个信息位、4×4 交织矩阵和 8 位突发；所有输出将来自后端生产算法。</p></section>}
      {result && <>
        <section className="stage10-panel" aria-labelledby="stage11-flow-title"><div className="stage10-heading"><h2 id="stage11-flow-title">信号处理流程</h2><span className="stage10-badge">seed {result.parameters.seed}</span></div>
          <ol className="stage11-flow">{['信息位', '卷积编码', '块交织', '突发错误信道', '反交织', 'Viterbi 译码'].map(step => <li key={step}>{step}</li>)}</ol>
          <MetricGrid items={[
            { label: '原始信息位', value: result.lengths.information_bits, hint: `尾位 ${result.lengths.tail_bits} 不计入信息位 BER` },
            { label: '有效编码位', value: result.lengths.encoded_bits, hint: 'Stage10 K=3、(7,5) 编码' },
            { label: '物理传输位', value: result.lengths.transmitted_bits, hint: `填充 ${result.lengths.padding_bits} 位` },
            { label: '交织器尺寸', value: `${result.interleaver.rows} × ${result.interleaver.columns}`, hint: `${result.interleaver.block_bits} 位/块` },
          ]} />
        </section>
        <section className="stage10-panel"><div className="stage10-heading"><h2>交织前后与突发错误位置</h2><span className="stage10-badge">按真实来源索引映射</span></div>
          <MetricGrid items={[
            { label: '实际注入错误', value: result.channel.flipped_count, hint: `传输索引 ${formatIndices(result.channel.flipped_positions)}` },
            { label: '反交织后有效码位错误', value: result.results.coded_error_count, hint: `编码索引 ${formatIndices(result.results.coded_error_indices_after_deinterleave)}` },
            { label: '译码后信息错误', value: result.results.information_error_count, hint: `信息索引 ${formatIndices(result.results.decoded_information_error_indices)}`, tone: result.results.corrected_all_information_errors ? 'good' : 'warning' },
            { label: '信息 BER', value: result.results.information_ber.toPrecision(4), hint: `${result.results.information_ber_errors} / ${result.results.information_ber_denominator} 信息位` },
          ]} />
          <ChartFrame title="传输位置 → 编码位置" description="每个传输坐标由 API 返回的排列来源表映射；填充位置显示为“填充”。" xLabel="传输序列索引" yLabel="映射" className="stage11-chart">
            <MappingView result={result} />
          </ChartFrame>
          <SequenceView result={result} />
        </section>
        <section className="stage10-panel stage10-review"><div className="stage10-heading"><h2>本次实验复盘</h2><span className="stage10-badge">生产链路结果</span></div>
          <div className="stage10-lesson"><p>{result.teaching.mapping}</p><p>{result.teaching.burst}</p><p>{result.teaching.conclusion}</p><p>{result.results.corrected_all_information_errors ? '本次实验中 Viterbi 恢复了全部信息位。' : `本次仍有 ${result.results.information_error_count} 个信息位错误。`}</p><p>{result.teaching.limitation}</p></div>
        </section>
      </>}
    </main>
  </div>
}

function formatIndices(indices: number[]) { return indices.length ? indices.join(', ') : '无' }

function MappingView({ result }: { result: Stage11Result }) {
  const total = result.lengths.transmitted_bits
  const start = result.channel.burst_start
  const lo = Math.max(0, Math.min(start - 24, total - 160))
  const hi = Math.min(total, Math.max(160, start + result.channel.burst_length + 24), lo + 256)
  const errors = new Set(result.channel.flipped_positions)
  return <svg viewBox={`0 0 720 ${Math.max(64, Math.ceil((hi - lo) / 16) * 22 + 28)}`} role="img" aria-label={`突发传输坐标 ${formatIndices(result.channel.flipped_positions)} 对应编码坐标 ${formatIndices(Object.values(result.channel.transmission_to_coded_index).filter((value): value is number => value !== null))}`}>
    {Array.from({ length: hi - lo }, (_, offset) => { const index = lo + offset, x = 18 + offset % 16 * 43, y = 12 + Math.floor(offset / 16) * 22, source = result.interleaver.output_sources[index], changed = errors.has(index); return <g key={index}><rect x={x} y={y} width="37" height="18" rx="3" className={changed ? 'stage11-map-error' : source === null ? 'stage11-map-pad' : 'stage11-map-cell'} /><text x={x + 18.5} y={y + 13} textAnchor="middle">{source === null ? '填' : source}</text><title>传输索引 {index} → {source === null ? '填充位' : `编码索引 ${source}`}{changed ? '，已翻转' : ''}</title></g> })}
    <text x="18" y={Math.ceil((hi - lo) / 16) * 22 + 24}>显示传输索引 {lo}–{hi - 1} / {total}</text>
  </svg>
}

function SequenceView({ result }: { result: Stage11Result }) {
  const total = result.details.transmitted_bits.length, start = result.channel.burst_start
  const from = total <= 256 ? 0 : Math.max(0, Math.min(start - 32, total - 224))
  const to = Math.min(total, from + 224)
  const badTx = new Set(result.channel.flipped_positions), badCode = new Set(result.results.coded_error_indices_after_deinterleave), badInfo = new Set(result.results.decoded_information_error_indices)
  const rows = [
    { label: '编码后有效比特', bits: result.details.encoded_bits, origin: from, errors: badCode },
    { label: '交织后传输序列', bits: result.details.interleaved_bits, origin: from, errors: badTx },
    { label: '突发信道输出', bits: result.details.transmitted_bits, origin: from, errors: badTx },
    { label: '反交织有效编码位', bits: result.details.deinterleaved_bits, origin: from, errors: badCode },
    { label: 'Viterbi 信息位输出', bits: result.details.decoded_information_bits, origin: 0, errors: badInfo },
  ]
  return <div className="stage11-sequences" aria-label="编码、传输、反交织和译码比特序列">{rows.map(row => <div className="stage11-sequence-row" key={row.label}><strong>{row.label}</strong><div className="stage11-bits">{row.bits.slice(row.origin, Math.min(row.bits.length, row.origin + (row.label.includes('信息位') ? 224 : to))).map((bit, index) => { const absolute = row.origin + index, changed = row.errors.has(absolute); return <span key={absolute} className={changed ? 'is-error' : ''} title={`索引 ${absolute}${changed ? '，错误/突发位置' : ''}`}>{bit}</span> })}</div></div>)}
    {from > 0 || to < total ? <p className="stage10-note">序列较长，以上显示与突发位置相邻的最多 224 个传输位；指标与错误索引按完整帧统计。</p> : null}
  </div>
}
