import { useState } from 'react'
import './App.css'
import { apiRequest, apiUrl } from './api'
import { ChartFrame, MetricGrid } from './DataViz'
import { formatBer } from './dataVizUtils'

interface SimulationResult {
  eb_n0_db: number
  n_bits: number
  n_errors: number
  ber_theoretical: number
  ber_measured: number
  seed: number | null
  rx_samples: number[]
  tx_symbols_samples: number[]
}

function App() {
  const [ebN0, setEbN0] = useState<number>(8)
  const [nBits, setNBits] = useState<number>(10000)
  const [seed, setSeed] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string>('')
  const [result, setResult] = useState<SimulationResult | null>(null)

  const runSimulation = async () => {
    setLoading(true)
    setError('')
    setResult(null)

    try {
      // 验证随机种子
      let seedValue: number | null = null
      if (seed.trim() !== '') {
        // 检查是否为有效的非负整数
        if (!/^\d+$/.test(seed.trim())) {
          throw new Error('随机种子必须是非负整数')
        }

        seedValue = parseInt(seed.trim(), 10)

        // 检查是否在安全整数范围内
        if (!Number.isSafeInteger(seedValue) || seedValue < 0) {
          throw new Error('随机种子必须在0到9007199254740991之间')
        }
      }

      const requestBody = {
        eb_n0_db: ebN0,
        n_bits: nBits,
        seed: seedValue,
        sample_size: 1000
      }

      const data = await apiRequest<SimulationResult>(apiUrl('/api/simulate'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      })

      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>CommDoctor</h1>
        <p className="subtitle">数字通信故障诊断教学平台 - BPSK通信仿真</p>
      </header>

      <div className="container">
        <section className="controls">
          <h2>仿真参数</h2>

          <div className="control-group">
            <label htmlFor="ebN0">
            Eb/N0 (信噪比，dB): <strong>{ebN0}</strong>
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
            <label htmlFor="seed">随机种子（可选，用于复现实验）:</label>
            <input
              id="seed"
              type="text"
              placeholder="留空则随机"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
            />
          </div>

          <button
            className="simulate-btn"
            onClick={runSimulation}
            disabled={loading}
          >
            {loading ? '仿真中...' : '开始仿真'}
          </button>

          {error && (
            <div className="error-message" role="alert">
              ⚠️ {error}
            </div>
          )}
        </section>

        {result && (
          <>
            <section className="results">
              <h2>仿真结果</h2>

              <MetricGrid className="result-grid" items={[
                { label: 'Eb/N₀', value: `${result.eb_n0_db.toFixed(1)} dB` },
                { label: '仿真比特数', value: result.n_bits.toLocaleString() },
                { label: '错误比特数', value: result.n_errors },
                { label: '理论 BER', value: formatBer(result.ber_theoretical, 4), tone: 'accent', hint: '相干 BPSK/AWGN' },
                { label: '实测 BER', value: formatBer(result.ber_measured, 4), tone: 'accent', hint: `${result.n_errors} errors / ${result.n_bits.toLocaleString()} bits` },
                ...(result.seed !== null ? [{ label: '随机种子', value: result.seed }] : []),
              ]} />
            </section>

            <section className="visualization">
              <h2>接收信号可视化</h2>
              <SignalChart rxSamples={result.rx_samples} txSymbols={result.tx_symbols_samples} />
            </section>
          </>
        )}
      </div>

      <footer className="footer">
        <p>CommDoctor · 阶段01 BPSK 通信仿真</p>
      </footer>
    </div>
  )
}

interface SignalChartProps {
  rxSamples: number[]
  txSymbols: number[]
}

function SignalChart({ rxSamples, txSymbols }: SignalChartProps) {
  const displayCount = Math.min(200, rxSamples.length)
  const samples = rxSamples.slice(0, displayCount)
  const symbols = txSymbols.slice(0, displayCount)

  // 计算显示范围
  const maxVal = Math.max(...samples.map(Math.abs), 3)
  const minVal = -maxVal
  const range = maxVal - minVal

  return (
    <ChartFrame title="接收样本与发送符号" xLabel="样本序号（前 200 点）" yLabel="幅度（归一化）" legend={[
      { label: '+1 符号接收值', color: '#6EE7B7' },
      { label: '−1 符号接收值', color: '#E9A568' },
      { label: '发送符号', color: '#38BDF8' },
    ]}>
      <svg width="100%" height="300" viewBox="0 0 800 300" role="img" aria-label="接收样本与发送符号波形">
        {/* 背景网格 */}
        <line x1="0" y1="150" x2="800" y2="150" stroke="#333" strokeWidth="1" />
        <line x1="0" y1="75" x2="800" y2="75" stroke="#222" strokeWidth="0.5" strokeDasharray="4" />
        <line x1="0" y1="225" x2="800" y2="225" stroke="#222" strokeWidth="0.5" strokeDasharray="4" />

        {/* 发送符号（背景） */}
        {symbols.map((symbol, i) => {
          const x = (i / displayCount) * 800
          const y = 150 - (symbol / range) * 280
          return (
            <circle
              key={`tx-${i}`}
              cx={x}
              cy={y}
              r="2"
              fill="#38BDF8"
              opacity="0.3"
            />
          )
        })}

        {/* 接收样本 */}
        {samples.map((sample, i) => {
          const x = (i / displayCount) * 800
          const y = 150 - (sample / range) * 280
          const color = symbols[i] > 0 ? '#6EE7B7' : '#E9A568'
          return (
            <circle
              key={`rx-${i}`}
              cx={x}
              cy={y}
              r="3"
              fill={color}
              opacity="0.7"
            />
          )
        })}

        {/* 坐标标签 */}
        <text x="5" y="15" fill="#888" fontSize="12">+{maxVal.toFixed(1)}</text>
        <text x="5" y="155" fill="#888" fontSize="12">0</text>
        <text x="5" y="295" fill="#888" fontSize="12">-{maxVal.toFixed(1)}</text>
      </svg>

    </ChartFrame>
  )
}

export default App
