# Stage13 LMS 自适应均衡实验室验收报告

日期：2026-10-27
仓库：`D:\CommDoctor\projects\CommDoctor-main`
分支：`main`
基线：`7d76573409a3cb1a94492e150d5a8e35f2302ddd`（与 `origin/main` 一致）

## 本轮交付

- `backend/stage13_lms.py`：独立 LMS 核心，复用 Stage09 静态 BPSK、RRC、full convolution 和同一接收帧生成逻辑。
- `backend/tests/oracles/stage13_lms_oracle.py`：不导入生产均衡器的标量更新参考。
- `backend/test_stage13_lms.py`、`backend/test_stage13_experiments_api.py`：更新公式、索引边界、复现性、训练/评估分离、统计分母、非法输入和 API 契约测试。
- `backend/main.py`：`POST /api/stage13/experiments`，有界参数、有限数值校验和发散诊断。
- `frontend/src/Stage13LmsApp.tsx`、`Stage13Lms.css`：`#/stage13` 参数控制、真实 MSE 曲线、raw/LMS BER、错误数/分母、训练诊断和教学复盘。
- `frontend/src/Router.tsx`、`AppShell.tsx`：Stage13 路由与导航。

## 数学契约

- 窗口顺序为 oldest-to-newest，5 个符号；均衡器初始系数全零。
- 窗口中心对应固定 2-symbol decision delay；训练只使用 pilot 的完整窗口，训练更新次数为请求的 `n_training_symbols`，范围 16–60。
- `y = w^T u`，`e = d - y`，`w_next = w + mu * e * u`；每个训练误差在更新前记录为 `e^2`。
- 训练结束后冻结系数；评估 payload 不参与更新。raw 与 LMS 使用同一 matched-filter 接收数组和同一 payload 位索引。
- BER 均为 `errors / compared`，默认 payload 分母 512；不把 pilot 或 guard 计入分母。
- seed 使用 `numpy.default_rng(seed)`，固定请求逐字段可复现。

## 自动化结果

- Stage13 核心/API + Stage09 定向回归：`25 passed`。
- 后端全量：`729 passed, 5 warnings`。警告来自既有 NumPy overflow 测试和 httpx deprecation，本轮未新增失败。
- 前端 `npm run lint`：通过。
- 前端 `npm run build`：通过（TypeScript/Vite production bundle）。
- `git diff --check`：通过。

## 实际数据试跑

请求 `seed=2026, Eb/N0=8 dB, training=60, payload=512, mu=0.01` 返回成功；训练末段 MSE 为 `0.3296`，同一帧 raw 为 `60/512`（BER `0.1172`），LMS 为 `63/512`（BER `0.1230`）。本次 LMS 结果退化，页面如实显示，未宣称普遍改善。

## 浏览器证据

- 受控 Chromium/Edge 可加载 `http://127.0.0.1:5173/#/stage13`；Stage13 标题、参数输入、运行按钮和 Stage01–Stage13 导航均可见。
- 可访问性树包含 5 个 spinbutton、运行按钮、当前阶段和导航链接；路由从 Stage13 到 Stage12 再回 Stage13 的声明式导航已执行。
- 375×812、768×1024、1440×900 视口均完成页面加载采集；未观察到页面脚本错误。
- **未验证**：自动点击后的结果区和 API 请求在浏览器场景采集器中未闭合，等待结果步骤超时且未捕获 `/api/stage13/experiments`；因此不声称浏览器主流程、结果曲线与 API DOM 一致性已通过。直接 HTTP API 试跑已通过。

## Git 门槛

本轮未提交、未推送。原因是用户规定只有核心测试、回归、前端检查和必要浏览器主流程全部通过后才允许提交推送；浏览器主流程证据仍未闭合。工作区既有未跟踪文件和报告均保留，未执行清理或覆盖。

## 剩余事项

复核浏览器场景采集器为何未触发 fetch，完成结果 DOM、参数修改、非法输入、服务失败和 375/768/1440 主流程验证后，再审查仅本轮相关文件并按要求设置 Author/Committer，最后提交和核验远端状态。

## 浏览器主流程补测（2026-10-27）

### 环境与页面

- 仓库仍为 `main`，HEAD 与 `origin/main` 均为 `7d76573409a3cb1a94492e150d5a8e35f2302ddd`；开始时工作区已有修改和未跟踪文件，本轮未暂存或清理。
- 本轮自启前端 `http://127.0.0.1:5174/#/stage13`、后端 `http://127.0.0.1:8000`；原报告所列 `5173` 未占用，另有一个本轮启动的后端探测实例在 `8001`。
- 受控 Chromium 156 页面实际 URL 为 `http://127.0.0.1:5174/#/stage13`。DOM 显示 Stage13 标题、5 项参数、运行按钮及导航。Stage12 导航和返回 Stage13 的点击有效。
- 浏览器场景证据 ID：`ev_da6e4d0c52f9e1f9ae9bfc1503affb5b491783a54b76928d14f017fe5bc5900f`。在等待运行按钮可见后点击，动作无工具错误，但 `/api/stage13/experiments` 没有网络事务；等待 `section.stage13-results` 10 秒超时，结果区未渲染。另一直接点击复现证据 ID：`ev_9ace6644e4434537be415a8bf5a7c51c64e9f5ff492a6b35d1f71db37d18cb24`，同样没有 Stage13 API 请求或结果 DOM。
- 浏览器控制台仅见 Vite 连接和 React DevTools 信息；无页面异常或控制台 error。采集器未暴露 API 请求/响应，因此没有可报告的浏览器 HTTP 状态码或响应 JSON。

### 本轮 API 实测（本地直连，不是浏览器事务）

通过 PowerShell 向 `POST http://127.0.0.1:8000/api/stage13/experiments` 发送脱敏参数 `{"seed":2026,"eb_n0_db":8,"n_training_symbols":60,"n_payload_symbols":512,"mu":0.01}`，收到成功 JSON：

- Raw：60 errors / 512 compared，BER `0.1171875`（60 ÷ 512）。
- LMS：63 errors / 512 compared，BER `0.123046875`（63 ÷ 512）；本次结果退化，照实保留。
- `training.errors` 与 `series.training_mse` 各 60 点；`series.raw_samples`、`series.equalized_samples` 各 512 点。训练首点 MSE `1.0`，`final_mse=0.329615072472224`，诊断文本明确说明末段训练误差不保证 BER 改善。
- 评估索引为 60–571，`same_channel_and_noise=true`；教学复盘文本为“本次 raw 为 60/512，LMS 为 63/512。”
- 由于浏览器未取得该响应，无法逐点比对结果 DOM、BER 文本或 SVG 曲线路径；数值与曲线一致性未在浏览器端验证。

### 未闭合项与判定

- 参数重跑和 seed 可复现性：浏览器按钮未触发 API，未完成；未把独立 API 测试冒充为页面参数重跑。
- 非法参数提示与服务不可用后的恢复：未完成。浏览器按钮未触发，故无法确认页面错误提示。
- 375px 下核心实验：未完成；本轮没有把页面加载检查记为运行通过。
- 浏览器自动化替代能力：仓库未安装 Playwright/Puppeteer，当前 Python 环境也无 Playwright/Selenium；未引入依赖。
- 本轮未修改生产代码。按钮调用失败可由受控浏览器场景复现，但现有浏览器自动化能力未能进一步区分页面交互问题与自动化点击行为，因此缺少足够证据按已确认的 P0/P1 缺陷修复。
- 最终判定：**PASS WITH LIMITATIONS**，仅本地 API 与初始 DOM/导航已验证；浏览器核心实验链仍未闭合，不建议据此进入提交阶段。
- 未提交、未推送、未暂存。已停止本轮启动的后端/前端进程；`8000`、`8001`、`5174` 均已确认释放。

## 提交前复核（2026-10-27，当前代码）

本轮针对学习率输入契约修复和提交前门槛重新执行了必要回归：

- `node frontend/check-stage13-input-contract.mjs`：通过；输出确认默认值 `0.01`、`min=0.00001`、`max=0.5`、`step=0.00001`，默认值落在原生 step 网格内。
- `python -m pytest -q test_stage13_lms.py test_stage13_experiments_api.py test_stage09_multipath_equalization.py test_stage09_multipath_oracle.py`：`25 passed`。
- `npm run lint`、`npm run build`、`git diff --check`：均通过；本轮未安装依赖。

### 真实浏览器主流程

在 `http://127.0.0.1:5174/#/stage13` 的受控浏览器中，初始学习率为 `0.01`。将输入改为 `0.00001` 后运行，结果区显示 `μ 0.00001`、Raw `60/512`、LMS `77/512`、末段 MSE `0.9986`；页面没有把退化结果宣称为改善。将输入改回默认 `0.01` 后再次运行，结果区显示 Raw `60/512`（BER `0.1172`）、LMS `63/512`（BER `0.1230`）、末段 MSE `0.3296`，并显示训练与评估分离说明。

将学习率输入改为 `0` 时，浏览器原生约束报告无效，`min=0.00001`、`step=0.00001`，未提交非法请求。默认参数的直接 HTTP API 响应为 Raw `60/512`、LMS `63/512`、`initial_mse=1.0`、`final_mse=0.329615072472224`、评估索引 `60–571`、`same_channel_and_noise=true`，与结果 DOM 文本一致。该浏览器页面本轮未捕获控制台 error。

本次复核未发现 P0/P1 阻断问题。此前场景采集器未能触发 fetch 的限制仍保留在上文作为历史记录；服务不可用恢复和多视口完整运行链未作为本轮新增证据，属于未扩大的 P2/P3 验收限制，不改变本次已验证的 Stage13 提交范围。
