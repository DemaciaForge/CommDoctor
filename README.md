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

当前测试覆盖:
- 阶段01: 91项测试
- 阶段02: 61项新增测试
- 总计: 152项测试

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

## 开发说明

本项目由AI辅助开发（Claude Code）。

## 许可证

待定
