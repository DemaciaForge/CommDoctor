# Stage09 多径信道与 ISI 均衡实验室验收报告

日期：2026-10-25
仓库：`D:\CommDoctor\projects\CommDoctor-main`

## 交付范围

本轮完成 Stage09 后端、前端和验收材料：

- `backend/multipath_equalization.py`：独立过采样 BPSK/RRC 静态多径模型、full convolution、pilot 回归、ZF/MMSE、固定 BER 索引和进程内实验缓存。
- `backend/main.py`：新增 Stage09 请求模型及实验创建、pilot 测量、均衡、反馈 API，并保留 404/409/422 错误语义和 challenge 信息隐藏。
- `backend/test_stage09_multipath_oracle.py`：独立数学 oracle 与边界测试。
- `backend/test_stage09_multipath_equalization.py`：Stage09 API/行为专项测试。
- `frontend/src/MultipathEqualizationApp.tsx`、`frontend/src/MultipathEqualization.css`：`#/stage09` 实验页面，包含观察、pilot 测量、ZF/MMSE、BER 和复盘。
- `frontend/src/Router.tsx`、`frontend/src/AppShell.tsx`：Stage09 路由和导航接入。

## 数学和数据口径

模型使用 16 samples/symbol、RRC rolloff 0.35、span 8 Ts、两径默认延迟 `[0, 16]` samples 和增益 `[1.0, 0.7]`，路径增益做 L2 归一化。发送端和接收端 RRC 各有 64 samples 群延迟，合计 128 samples；信道和匹配滤波均保留 full convolution 尾部。

每个实验一次生成并缓存同一帧、同一噪声、同一 matched-filter 数组。pilot 和 payload 分离，payload 使用后端固定的 `payload_sample_indices`；Raw、ZF、MMSE 使用完全相同的有效样本集合。均衡器用 pilot 内部完整的 5-symbol 窗训练，ZF 解 `XᵀXw=Xᵀt`，MMSE 解 `(XᵀX+λI)w=Xᵀt`，其中 `λ` 为噪声方差。生产均衡器没有被用于 oracle。

## 自动化验证

- Stage09 专项：`python -m pytest -q test_stage09_multipath_oracle.py test_stage09_multipath_equalization.py`（在 `backend` 目录执行）→ **12 passed**。
- 后端全量：`python -m pytest -q`（在 `backend` 目录执行）→ **549 passed, 5 warnings**。警告是已有 NumPy overflow 和 httpx deprecation warning，没有本轮新增失败。
- 前端：`npm run lint` → 通过；`npm run build` → 通过，TypeScript/Vite production bundle 成功。
- Impeccable detector：对四个修改后的前端文件执行 `detect --json` → `[]`，未报告问题。

## 真实浏览器验收

本地服务：后端 `http://127.0.0.1:8000`，前端 `http://127.0.0.1:5173`，Codex in-app browser tab 1。

在引导模式以 8 dB、512 payload、seed 2026 创建实验，浏览器实际完成：

1. 创建实验并显示发送/接收/匹配滤波波形、静态冲激响应、延迟和有效索引。
2. 点击“用 pilot 测量信道”：训练行数 60、条件数 7.24、训练残差 RMS 0.3663、MMSE λ 0.0792。
3. 点击“运行 ZF”和“运行 MMSE”：两个 API 操作均成功。
4. 页面显示 Raw `53/512`（`1.035e-1`）、ZF `7/512`（`1.367e-2`）、MMSE `7/512`（`1.367e-2`），并显示教学复盘。
5. 后端日志确认对应 OPTIONS/POST/GET 请求均为 HTTP 200。
6. 直接请求不存在实验 ID 的 estimate 端点返回 HTTP 404，错误状态契约可用。
7. 导航到 `#/stage08` 后返回 `#/stage09` 成功；直接重新加载 `#/stage09` 返回空实验状态。
8. 视口检查使用 375×812、768×1024、1440×900：文档 `scrollWidth` 分别为 360、753、1425，均等于视口扣除浏览器侧边布局后的 clientWidth，没有页面级横向溢出。
9. `tab.dev.logs({levels:['error','warning','warn']})` 返回空数组。此前页面初始化时出现过一个与应用无关的 Statsig `userID` warning；本次流程没有项目错误日志。

键盘焦点的自动化探针受当前 in-app Playwright 包装器限制，未能稳定取得完整 Tab 序列，因此标记为**未验证**；页面控件仍具有原生 button/input/select 语义和可见 focus 样式。

## 已知边界

模型当前覆盖静态实数 BPSK、整数符号延迟（16 samples 的倍数）、固定 RRC 和短窗线性均衡器；不覆盖分数延迟、时变信道、载波偏移或编码。均衡不保证每个 seed/SNR 都改善 BER。冲激响应图的横轴是返回数组位置，延迟信息在旁边单独显示。单进程缓存最多保留 20 个实验。

## Git 发布记录

功能提交：`a3cbb797f88912828044423bb15f81cf3d07922b`，作者和 committer 均为 `DemaciaForge <DemaciaForge@users.noreply.github.com>`。本报告随后作为独立文档提交；最终本地 `HEAD` 与 `origin/main` 均为报告提交 SHA，且 `git ls-remote origin refs/heads/main` 已核对一致。工作区原有 `.agents/`、`.codex/`、`AGENTS.md` 及旧报告保持未跟踪，不纳入提交。
