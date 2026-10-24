import { useState } from 'react'
import './App.css'
import './FaultDiagnosis.css'
import { apiRequest, apiUrl } from './api'
import { MetricGrid, formatBer } from './DataViz'

interface DiagnosisResult {
  experiment_id: string
  eb_n0_db: number
  n_bits: number
  dc_offset: number
  seed: number | null
  noise_std: number
  normal: {
    ber: number
    n_errors: number
    threshold: number
  }
  with_fault: {
    ber: number
    n_errors: number
    threshold: number
  }
  measurement: {
    rx_mean: number
    noise_std: number
  }
  diagnosis: {
    has_dc_offset: boolean
    estimated_offset: number
    confidence: string
    message: string
    suggested_threshold: number
    evidence: {
      rx_mean: number
      std_error: number
      threshold_3sigma: number
      n_samples: number
    }
  }
  repaired: {
    ber: number
    n_errors: number
    threshold: number
  }
  ber_theoretical: number
  samples: {
    tx_symbols: number[]
    rx_normal: number[]
    rx_with_fault: number[]
  }
}

interface CustomThresholdResult {
  ber: number
  n_errors: number
  threshold: number
}

function FaultDiagnosisApp() {
  // 通信参数
  const [ebN0, setEbN0] = useState<number>(8)
  const [nBits, setNBits] = useState<number>(10000)
  const [seed, setSeed] = useState<string>('42')

  // 故障参数
  const [dcOffset, setDcOffset] = useState<number>(0.8)
  const [faultEnabled, setFaultEnabled] = useState<boolean>(false)

  // 修复参数
  const [customThreshold, setCustomThreshold] = useState<number>(0.0)

  // 状态
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string>('')
  const [result, setResult] = useState<DiagnosisResult | null>(null)
  const [customResult, setCustomResult] = useState<CustomThresholdResult | null>(null)

  const runDiagnosisExperiment = async () => {
    setLoading(true)
    setError('')
    setResult(null)
    setCustomResult(null)

    try {
      let seedValue: number | null = null
      if (seed.trim() !== '') {
        if (!/^\d+$/.test(seed.trim())) {
          throw new Error('随机种子必须是非负整数')
        }
        seedValue = parseInt(seed.trim(), 10)
        if (!Number.isSafeInteger(seedValue) || seedValue < 0) {
          throw new Error('随机种子必须在0到9007199254740991之间')
        }
      }

      const requestBody = {
        eb_n0_db: ebN0,
        n_bits: nBits,
        dc_offset: faultEnabled ? dcOffset : 0.0,
        seed: seedValue,
        sample_size: 1000
      }

      const data = await apiRequest<DiagnosisResult>(apiUrl('/api/fault-diagnosis'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      })

      setResult(data)
      setCustomThreshold(data.diagnosis.suggested_threshold)
    } catch (err) {
      setError(err instanceof Error ? err.message : '未知错误')
    } finally {
      setLoading(false)
    }
  }

  const applyCustomThreshold = async () => {
    if (!result) return

    try {
      const data = await apiRequest<CustomThresholdResult>(apiUrl('/api/apply-threshold'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          experiment_id: result.experiment_id,
          threshold: customThreshold
        }),
      })

      setCustomResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '未知错误')
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>CommDoctor</h1>
        <p className="subtitle">数字通信故障诊断教学平台 - 阶段02：DC偏移故障诊断与修复</p>
      </header>

      <div className="container fault-diagnosis-container">
        {/* 第一部分：通信参数 */}
        <section className="controls-section">
          <h2>1. 通信参数设置</h2>

          <div className="control-group">
            <label htmlFor="ebN0">
              Eb/N0（信噪比，dB）：<strong>{ebN0}</strong>
            </label>
            <input
              id="ebN0"
              type="range"
              min="-10"
              max="30"
              step="0.5"
              value={ebN0}
              onChange={(e) => setEbN0(parseFloat(e.target.value))}
            />
          </div>

          <div className="control-group">
            <label htmlFor="nBits">仿真比特数:</label>
            <select
              id="nBits"
              value={nBits}
              onChange={(e) => setNBits(parseInt(e.target.value))}
            >
              <option value={1000}>1,000</option>
              <option value={10000}>10,000</option>
              <option value={50000}>50,000</option>
              <option value={100000}>100,000</option>
            </select>
          </div>

          <div className="control-group">
            <label htmlFor="seed">随机种子:</label>
            <input
              id="seed"
              type="text"
              placeholder="留空则随机"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
            />
          </div>
        </section>

        {/* 第二部分：故障注入控制 */}
        <section className="fault-control-section">
          <h2>2. 故障注入控制</h2>

          <div className="fault-toggle">
            <label className="switch">
              <input
                type="checkbox"
                aria-label="启用 DC 偏移故障注入"
                aria-describedby="fault-status"
                checked={faultEnabled}
                onChange={(e) => setFaultEnabled(e.target.checked)}
              />
              <span className="slider"></span>
            </label>
            <span id="fault-status" className="fault-status" aria-live="polite">
              {faultEnabled ? '✗ 已注入DC偏移故障' : '✓ 无故障'}
            </span>
          </div>

          {faultEnabled && (
            <div className="control-group">
              <label htmlFor="dcOffset">
                DC 偏移（接收信号的恒定 I 路偏置）: <strong>{dcOffset.toFixed(2)}</strong>
              </label>
              <input
                id="dcOffset"
                type="range"
                min="-1.0"
                max="1.0"
                step="0.05"
                value={dcOffset}
                onChange={(e) => setDcOffset(parseFloat(e.target.value))}
              />
              <div className="hint">建议初始值: +0.8</div>
            </div>
          )}

          <button
            className="run-experiment-btn"
            onClick={runDiagnosisExperiment}
            disabled={loading}
          >
            {loading ? '运行中...' : '运行诊断实验'}
          </button>

          {error && (
            <div className="error-message" role="alert">
              ⚠️ {error}
            </div>
          )}
        </section>

        {result && (
          <>
            {/* 第三部分：接收信号可视化 */}
            <section className="visualization-section">
              <h2>3. 接收信号可视化</h2>
              <SignalComparisonChart samples={result.samples} />
            </section>

            {/* 第四部分：主动测量与诊断证据 */}
            <section className="measurement-section">
              <h2>4. 主动测量与诊断</h2>

              <MetricGrid className="measurement-grid" items={[
                { label: '接收信号均值', value: result.measurement.rx_mean.toFixed(4), hint: 'I 路幅度' },
                { label: '噪声标准差', value: result.noise_std.toFixed(4), hint: 'σ' },
                { label: '均值 3σ 界限', value: `±${result.diagnosis.evidence.threshold_3sigma.toFixed(4)}`, hint: `${result.diagnosis.evidence.n_samples.toLocaleString()} samples` },
                { label: '置信度', value: result.diagnosis.confidence, tone: result.diagnosis.has_dc_offset ? 'warning' : 'good' },
              ]} />

              <div className={`diagnosis-box ${result.diagnosis.has_dc_offset ? 'has-fault' : 'no-fault'}`}>
                <div className="diagnosis-icon">
                  {result.diagnosis.has_dc_offset ? '⚠️' : '✓'}
                </div>
                <div className="diagnosis-content">
                  <h3>{result.diagnosis.has_dc_offset ? '检测到DC偏移故障' : '未检测到显著偏移'}</h3>
                  <p>{result.diagnosis.message}</p>
                  {result.diagnosis.has_dc_offset && (
                    <div className="diagnosis-details">
                      <p><strong>估计偏移:</strong> {result.diagnosis.estimated_offset.toFixed(4)}</p>
                      <p><strong>建议门限:</strong> {result.diagnosis.suggested_threshold.toFixed(4)}</p>
                    </div>
                  )}
                </div>
              </div>
            </section>

            {/* 第五部分：接收机修复控制 */}
            <section className="repair-section">
              <h2>5. 接收机修复</h2>

              <div className="repair-controls">
                <div className="control-group">
                  <label htmlFor="customThreshold">
                    判决门限（把接收值分成 0/1 的参考线）: <strong>{customThreshold.toFixed(2)}</strong>
                  </label>
                  <input
                    id="customThreshold"
                    type="range"
                    min="-1.5"
                    max="1.5"
                    step="0.05"
                    value={customThreshold}
                    onChange={(e) => setCustomThreshold(parseFloat(e.target.value))}
                  />
                </div>

                <button
                  className="apply-threshold-btn"
                  onClick={applyCustomThreshold}
                >
                  应用自定义门限
                </button>

                <button
                  className="suggested-threshold-btn"
                  onClick={() => {
                    const suggestedValue = result.diagnosis.suggested_threshold
                    setCustomThreshold(suggestedValue)
                    // 直接使用确定的值，避免闭包读取旧 state
                    void apiRequest<CustomThresholdResult>(apiUrl('/api/apply-threshold'), {
                        method: 'POST',
                        headers: {
                          'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                          experiment_id: result.experiment_id,
                          threshold: suggestedValue
                        }),
                      }).then(data => setCustomResult(data)).catch(err => setError(err instanceof Error ? err.message : '操作失败，请重试'))
                  }}
                >
                  使用建议门限
                </button>
              </div>
            </section>

            {/* 第六部分：BER对比 */}
            <section className="comparison-section">
              <h2>6. 修复前后BER对比</h2>

              <div className="ber-comparison-grid">
                <div className="ber-card baseline">
                  <div className="card-header">理论基准</div>
                  <div className="card-body">
                    <div className="ber-value-large">{formatBer(result.ber_theoretical)}</div>
                    <div className="ber-details">
                      <p>无故障BPSK/AWGN理论BER</p>
                    </div>
                  </div>
                </div>

                <div className="ber-card normal">
                  <div className="card-header">正常无故障</div>
                  <div className="card-body">
                    <div className="ber-value-large">
                      {formatBer(result.normal.ber)}
                    </div>
                    <div className="ber-details">
                      <p>错误比特: {result.normal.n_errors}</p>
                      <p>判决门限: {result.normal.threshold.toFixed(2)}</p>
                    </div>
                  </div>
                </div>

                <div className="ber-card fault">
                  <div className="card-header">故障注入后</div>
                  <div className="card-body">
                    <div className="ber-value-large">
                      {formatBer(result.with_fault.ber)}
                    </div>
                    <div className="ber-details">
                      <p>错误比特: {result.with_fault.n_errors}</p>
                      <p>DC偏移: {result.dc_offset.toFixed(2)}</p>
                      <p>判决门限: {result.with_fault.threshold.toFixed(2)}</p>
                    </div>
                  </div>
                </div>

                <div className="ber-card repaired">
                  <div className="card-header">自动修复后</div>
                  <div className="card-body">
                    <div className="ber-value-large">
                      {formatBer(result.repaired.ber)}
                    </div>
                    <div className="ber-details">
                      <p>错误比特: {result.repaired.n_errors}</p>
                      <p>判决门限: {result.repaired.threshold.toFixed(2)}</p>
                      <p className={result.repaired.ber < result.with_fault.ber ? 'improvement' : 'degradation'}>
                        {result.repaired.ber < result.with_fault.ber ? '↓ 改善' : '↑ 变化'}:
                        {' '}
                        {result.with_fault.ber > 0
                          ? ((1 - result.repaired.ber / result.with_fault.ber) * 100).toFixed(1) + '%'
                          : 'N/A'}
                      </p>
                    </div>
                  </div>
                </div>

                {customResult && (
                  <div className="ber-card custom">
                    <div className="card-header">自定义门限修复</div>
                    <div className="card-body">
                      <div className="ber-value-large">
                        {formatBer(customResult.ber)}
                      </div>
                      <div className="ber-details">
                        <p>错误比特: {customResult.n_errors}</p>
                        <p>判决门限: {customResult.threshold.toFixed(2)}</p>
                        <p className={customResult.ber < result.with_fault.ber ? 'improvement' : 'degradation'}>
                          {customResult.ber < result.with_fault.ber ? '↓ 改善' : '↑ 变化'}:
                          {' '}
                          {result.with_fault.ber > 0
                            ? ((1 - customResult.ber / result.with_fault.ber) * 100).toFixed(1) + '%'
                            : 'N/A'}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="comparison-notes">
                <h4>说明:</h4>
                <ul>
                  <li>所有对比均基于同一批发送数据和噪声</li>
                  <li>修复效果取决于偏移量、噪声水平和样本量</li>
                  <li>小样本或小偏移时，修复可能不明显</li>
                  <li>允许修复未成功或修复后更差的情况</li>
                </ul>
              </div>
            </section>
          </>
        )}
      </div>

      <footer className="footer">
        <p>CommDoctor · 阶段02 DC 偏移故障诊断与修复</p>
      </footer>
    </div>
  )
}

interface SignalComparisonChartProps {
  samples: {
    tx_symbols: number[]
    rx_normal: number[]
    rx_with_fault: number[]
  }
}

function SignalComparisonChart({ samples }: SignalComparisonChartProps) {
  const displayCount = Math.min(150, samples.rx_normal.length)
  const txSymbols = samples.tx_symbols.slice(0, displayCount)
  const rxNormal = samples.rx_normal.slice(0, displayCount)
  const rxFault = samples.rx_with_fault.slice(0, displayCount)

  const maxVal = Math.max(
    ...rxNormal.map(Math.abs),
    ...rxFault.map(Math.abs),
    3
  )
  const minVal = -maxVal
  const range = maxVal - minVal

  return (
    <div className="chart-comparison">
      <div className="chart-box">
        <h4>正常接收信号</h4>
        <svg width="100%" height="250" viewBox="0 0 600 250">
          <line x1="0" y1="125" x2="600" y2="125" stroke="#333" strokeWidth="1" />
          <line x1="0" y1="62.5" x2="600" y2="62.5" stroke="#222" strokeWidth="0.5" strokeDasharray="2" />
          <line x1="0" y1="187.5" x2="600" y2="187.5" stroke="#222" strokeWidth="0.5" strokeDasharray="2" />

          {rxNormal.map((sample, i) => {
            const x = (i / displayCount) * 600
            const y = 125 - (sample / range) * 230
            const color = txSymbols[i] > 0 ? '#6EE7B7' : '#E9A568'
            return (
              <circle
                key={i}
                cx={x}
                cy={y}
                r="2.5"
                fill={color}
                opacity="0.7"
              />
            )
          })}
        </svg>
      </div>

      <div className="chart-box">
        <h4>故障注入后接收信号</h4>
        <svg width="100%" height="250" viewBox="0 0 600 250">
          <line x1="0" y1="125" x2="600" y2="125" stroke="#333" strokeWidth="1" />
          <line x1="0" y1="62.5" x2="600" y2="62.5" stroke="#222" strokeWidth="0.5" strokeDasharray="2" />
          <line x1="0" y1="187.5" x2="600" y2="187.5" stroke="#222" strokeWidth="0.5" strokeDasharray="2" />

          {rxFault.map((sample, i) => {
            const x = (i / displayCount) * 600
            const y = 125 - (sample / range) * 230
            const color = txSymbols[i] > 0 ? '#6EE7B7' : '#E9A568'
            return (
              <circle
                key={i}
                cx={x}
                cy={y}
                r="2.5"
                fill={color}
                opacity="0.7"
              />
            )
          })}
        </svg>
      </div>

      <div className="chart-axis-note">纵轴：接收幅度（归一化） · 横轴：样本序号（前 150 点）</div>

      <div className="chart-legend">
        <span><span className="legend-dot green"></span> +1符号接收值</span>
        <span><span className="legend-dot orange"></span> -1符号接收值</span>
      </div>
    </div>
  )
}

export default FaultDiagnosisApp
