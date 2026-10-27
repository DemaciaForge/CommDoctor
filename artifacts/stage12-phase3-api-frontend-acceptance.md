# CommDoctor Stage12 Phase 3：API 与前端软判决性能对比验收

日期：2026-10-27（Asia/Shanghai）

仓库：`D:\CommDoctor\projects\CommDoctor-main`
分支：`main`

## 1. 初始与范围

开始检查时 HEAD、本地 `origin/main` 和 GitHub 实时 `refs/heads/main` 均为 `fd61951a710b5de39c856d7a98456d986c3ddb6c`，工作区没有已跟踪修改；已有 `.agents/`、`.codex/`、Stage01–Stage12 历史材料、Oracle、`design-system/` 等未跟踪文件均保留。本报告创建前确认 `artifacts/stage12-phase3-api-frontend-acceptance.md` 不存在。

本轮只新增 Stage12 API/实验核心、对应测试、Stage12 页面与样式、路由导航和本报告；没有修改 Stage10/Stage12 已通过的软判决核心、Phase 1 Oracle 或既有阶段语义。

## 2. API 与公平比较

新增无状态接口：

- `POST /api/stage12/compare`：默认 256 个信息位、4 dB、seed 2026，可选 `include_details`（最多 256 位）。请求严格拒绝未知字段、布尔冒充整数、非有限值、SNR 越界和帧长/详情超限。
- `POST /api/stage12/ber-sweep`：默认 0–10 dB、步长 2 dB、每点 2048 位、seed 2026；最多 16 点、4096 位/点、32768 个总信息位，扫描网格必须整除且递增。

实现复用 `convolutional_coding.encode_frame`、Stage10 固定 `K=3/(7,5)/R=1/2` 能量公式、`hard_decision` 和 `stage12_soft_viterbi.paired_decode`。单次实验只生成一次信息帧、编码帧和编码链路噪声；硬、软译码均接收同一个不可变样本 tuple。扫描复用同一个 payload，逐点只抽取一次噪声，并返回硬/软输入样本 SHA-256 摘要相同的证据。信息 BER 统一为 `information_error_count / n_information_bits`，两个零尾位不计入分母。

## 3. 本轮真实数据

直接调用 API：`n_information_bits=256, eb_n0_db=4, seed=2026`。

- 单次硬判决：`0/256`，BER `0.0`。
- 单次软判决：`0/256`，BER `0.0`。
- 两种信息输出一致；同一样本摘要和噪声抽样次数 `1`。

扫描调用：`start=0, stop=10, step=2, n_information_bits=512, seed=2026`。

| Eb/N0 (dB) | 硬判决 errors/N | 硬 BER | 软判决 errors/N | 软 BER |
|---:|---:|---:|---:|---:|
| 0 | 103/512 | 0.201171875 | 33/512 | 0.064453125 |
| 2 | 25/512 | 0.048828125 | 5/512 | 0.009765625 |
| 4 | 10/512 | 0.01953125 | 0/512 | 0 |
| 6 | 0/512 | 0 | 0/512 | 0 |
| 8 | 0/512 | 0 | 0/512 | 0 |
| 10 | 0/512 | 0 | 0/512 | 0 |

零误码在响应和 UI 中保留为真实 `0/N`，并说明“有限样本中未观察到错误”；没有将其改写为非零地板或真实概率结论。本次样本显示软判决在前 3 个点误码更少，但页面和报告不把有限样本结果表述为逐点保证。

## 4. 自动化验证

- Stage12 Oracle、软译码生产回归、Stage12 API：定向 `87 passed`。
- 完整后端：`716 passed, 5 warnings`。5 条 warning 均为既有 NumPy overflow 或 httpx DeprecationWarning，未修改无关历史 warning。
- `npm run lint`：通过。
- `npm run build`：通过，Vite 46 modules transformed，产物构建成功。
- `git diff --check`：通过；仅报告工作树中已有的 LF/CRLF 提示，无 whitespace error。

新增 API 测试覆盖固定 seed、共同样本摘要、独立 `paired_decode` 输出、尾位分母、错误区间/非有限值/超预算、扫描 payload 复用、每点一次译码、零误码和内部错误不泄露堆栈。

## 5. 前端与浏览器验收

新增页面 `#/stage12`，通过共享 `AppShell`、`apiRequest`、`ChartFrame`、`MetricGrid` 和现有导航进入。单次实验展示硬/软错误数、BER、分母、路径/能量摘要、共同样本证据和有限细节；扫描展示真实双曲线、逐点数据表、零误码标记及教学复盘。参数变化会清除旧结果，加载、HTTP 错误和服务不可用均有明确提示。

使用本轮启动的本地服务：后端 `127.0.0.1:8000`，前端 `127.0.0.1:5174`；使用本机 Microsoft Edge headless 浏览器执行真实 HTTP/DOM 验收：

- 默认单次、修改信息位数后重新运行：通过，旧结果先清除。
- 默认 6 点扫描、修改每点位数后重新扫描：通过，表格 6 行与 API 响应一致。
- Stage10 → Stage12 导航、Stage12 刷新：通过。
- 断开单次 API 后提交：通过，显示“无法连接实验服务。请确认后端已启动，然后重试。”。
- 375、768、1440 视口：`documentWidth == viewportWidth` 且 `bodyWidth == viewportWidth`，未发现页面横向溢出。
- 键盘 Tab：聚焦落在可操作导航链接，焦点可见；按钮/输入使用原生可聚焦控件。
- 页面 JavaScript 异常：0；真实 API 请求均返回 200（错误探针除外）。

Impeccable detector 对新增页面 TSX/CSS 未报告机械性设计问题。浏览器验收使用本地 Edge/headless；未执行真实移动设备、跨浏览器矩阵、并发负载或屏幕阅读器实机测试。

## 6. 限制与 Phase 4 条件

本轮不声称跨浏览器/真实设备/高并发性能结论；BER 仍是有限帧的 Monte Carlo 观测。Phase 4 可在需要时补充跨浏览器和更大样本的统计稳定性验证，但启动前必须保持本报告中的 API 公平性、尾位分母和零误码语义不变。

## 7. Git 状态

本轮验收结束时尚未提交或推送；本地 HEAD 和远端仍为 `fd61951a710b5de39c856d7a98456d986c3ddb6c`。提交前只应暂存本轮的 `backend/main.py`、`backend/stage12_experiments.py`、`backend/test_stage12_experiments_api.py`、`frontend/src/AppShell.tsx`、`frontend/src/Router.tsx`、`frontend/src/Stage12SoftDecisionApp.tsx`、`frontend/src/Stage12SoftDecision.css` 和本报告。已有未跟踪文件不得加入提交。
