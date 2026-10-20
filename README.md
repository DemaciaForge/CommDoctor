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

## 测试

```bash
cd backend
pytest -v
```

**完整测试覆盖**:
- 后端测试总数: **393** 项
  - 基础功能与Stage01: 118 项 (BPSK调制解调、AWGN信道、误码率计算、API基础)
  - 阶段02核心功能: 138 项 (DC偏移故障诊断、配对实验、修复验证、API集成)
  - 历史缺陷回归测试: 137 项 (AUD系列、P2系列、Round6-8边界与数值)

**测试通过情况**:
- ✓ 393 项全部通过
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

### Round13 修复：精确舍入

- 使用 binary64 精确整数比较避免舍入误差
- 所有理论BER计算采用 ties-to-even 舍入规则
- 包含 29 项历史oracle不一致案例的验证测试
- 负指数比较逻辑经过边界测试

### 历史缺陷修复保留

- **AUD4**: 非有限值输入验证
- **P2-F01~F04**: 空数组、溢出、复数、整数回绕修复
- **P2-B01~B09**: 空数组、类型检查、参数边界修复
- **Round6-8**: 类型系统、数值边界、API参数验证

## 开发说明

本项目由AI辅助开发（Claude Code）。

## 许可证

**待定** - 当前仓库未授予明确的开源使用、修改或再分发许可。

本仓库内容仅供参考，任何使用、修改或再分发请先咨询项目维护者。
