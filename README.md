# CommDoctor

数字通信故障诊断教学平台

## 项目简介

CommDoctor 是一个用于数字通信系统故障诊断教学的Web平台。通过可视化和交互式实验，帮助学习者理解通信系统中的故障现象、诊断方法和修复策略。

## 项目进度

### 阶段01：BPSK Web交互原型 ✓

- 真实BPSK调制解调
- AWGN信道模拟
- 理论与实测误码率计算
- 接收信号可视化
- 参数交互界面

### 阶段02：DC偏移故障诊断与修复 ✓

- DC偏移故障注入与控制
- 配对实验机制（同一批数据对比）
- 主动测量功能
- 基于证据的故障诊断
- 真实接收机修复（可调节判决门限）
- 修复前后BER量化对比
- 完整诊断-修复工作流

### 阶段03：交互式诊断挑战 MVP

- 后端随机生成 DC 偏移仿真实验，创建响应隐藏注入参数和诊断答案
- 查看真实 BPSK/AWGN 波形、基准与故障 BER，并主动请求均值/3σ测量证据
- 提交故障判断；错误时允许继续分析，正确后开放门限修复实验
- 基于同一批实验样本计算修复 BER，并展示参数、证据、机理和针对性反馈

## 技术栈

- **前端**：React + TypeScript + Vite
- **后端**：Python + FastAPI
- **数值计算**：NumPy + SciPy
- **测试**：pytest

## 快速开始

### 后端启动

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
python main.py
```

后端将运行在 http://127.0.0.1:8000

### 前端启动

```bash
cd frontend
npm install
npm run dev
```

前端将运行在 http://localhost:5173

## API文档

访问 http://127.0.0.1:8000/docs 查看交互式API文档（Swagger UI）

### 主要端点

- `GET /` - API根路径
- `GET /health` - 健康检查
- `POST /api/simulate` - 运行BPSK仿真（阶段01）
- `POST /api/fault-diagnosis` - 运行故障诊断实验（阶段02）
- `POST /api/apply-threshold` - 应用自定义判决门限（阶段02）
- `POST /api/challenges` - 创建 Stage03 DC 偏移挑战
- `GET /api/challenges/{challenge_id}/measurement` - 收集挑战测量证据
- `POST /api/challenges/diagnosis` - 提交挑战诊断
- `POST /api/challenges/repair` - 执行挑战门限修复
- `GET /api/challenges/{challenge_id}/feedback` - 查看完成后的教学复盘

前端可通过导航进入 `#/stage03`。Stage03 首版只生成 DC 偏移故障。

## 测试

```bash
cd backend
pytest -v
```

**完整测试覆盖**:
- 后端测试总数: **411** 项
  - 基础功能与Stage01: 118 项 (BPSK调制解调、AWGN信道、误码率计算、API基础)
  - 阶段02核心功能: 138 项 (DC偏移故障诊断、配对实验、修复验证、API集成)
  - 历史缺陷回归测试: 155 项 (AUD系列、P2系列、Round6-8边界与数值)

**测试通过情况**:
- ✓ 411 项全部通过
- ⚠ 5 项预期警告 (数值溢出、弃用库接口)

## 核心功能

### DC偏移故障模型

```
r = s + n + d
```

其中:
- `s`: 发送BPSK符号 (-1 或 +1)
- `n`: AWGN噪声
- `d`: DC偏移
- `r`: 接收信号

### 接收机修复

通过调整判决门限`T`进行修复:
- 判决规则: `r > T → 1, r ≤ T → 0`
- 理想情况: `T = d` 时恢复最优判决

### 配对实验保证

所有对比（正常、故障、修复）使用:
- 同一批发送比特
- 同一批发送符号
- 同一批噪声样本
- 仅改变DC偏移或门限

## 数值精度

### Round13 修复：标准误差正确舍入

CommDoctor 在故障诊断流程中需要计算标准误差（SE），其数学表达式为：

```
SE = sqrt((1 + σ²) / N)
```

其中 `σ` 为噪声标准差（binary64 浮点数），`N` 为样本数（精确整数）。

为确保数值正确性，实现采用以下算法：

- **精确有理数计算**：将 `σ²` 表示为精确有理数 `p²/q²`，使 SE² = `(p² + q²) / (q² * N)`
- **Binary64 正确舍入**：通过二分搜索 binary64 位编码，结合精确整数比较（避免浮点舍入误差），实现 IEEE 754 ties-to-even 舍入
- **独立 oracle 验证**：使用完全不同的算法结构（整数位长度 + `math.isqrt`）作为独立 oracle，交叉验证生产函数的正确性
- **数学证书**：对于 `noise_std=0, N=5` 的特殊情况，SE = `sqrt(1/5)` 的正确舍入结果通过精确整数不等式证明

验证覆盖：
- 41 项 Round8-13 边界测试（非正规数、正规数边界、负指数、中点舍入）
- 独立 oracle 与生产函数的完全一致性检查
- 参考实验脚本的数值保护测试

**注意**：理论 BER 计算（`0.5 * erfc(...)`）使用 SciPy 库函数，不在此精确舍入范围内。

### 历史缺陷修复保留

- **AUD4**: 非有限值输入验证
- **P2-F01~F04**: 空数组、溢出、复数、整数回绕修复
- **P2-B01~B09**: 空数组、类型检查、参数边界修复
- **Round6-8**: 类型系统、数值边界、API参数验证

## 开发说明

本项目由AI辅助开发（Claude Code）（codex）。

## 许可证

**待定** - 当前仓库未授予明确的开源使用、修改或再分发许可。

本仓库内容仅供参考，任何使用、修改或再分发请先咨询项目维护者。
