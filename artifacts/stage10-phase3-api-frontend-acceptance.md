# CommDoctor Stage10 Phase 3 API 与前端验收报告

日期：2026-10-25（Asia/Shanghai）  
仓库：`D:\CommDoctor\projects\CommDoctor-main`  
分支：`main`

## 范围与开始状态

本轮在 Phase 2 生产卷积编码、AWGN 与 Viterbi 模块上增加无状态 API 和 `#/stage10` 交互实验室，没有重写生产算法或修改 Phase 1 Oracle。开始检查时，本地 `HEAD` 和 `origin/main` 均为 `338496d45f8af858f8f3a84640f3479145c7521d`，分支为 `main`，tracked 工作区无已有修改、暂存区为空。工作区原有未跟踪的 `.agents/`、`.codex/`、`AGENTS.md`、Stage01–09 报告、Phase 1 方案/Oracle/测试等均未加入本轮提交；本轮 Skill 检查产生的 `design-system/commdoctor-stage10/MASTER.md` 也保留在工作区但未提交。

## 修改文件

- `backend/main.py`：Stage10 请求模型、中间件 JSON 内容类型校验挂接和 `POST /api/stage10/experiments`。
- `backend/test_stage10_api.py`：接口与错误处理专项测试。
- `frontend/src/Stage10CodingApp.tsx`、`frontend/src/Stage10Coding.css`：实验参数、加载/错误/空状态、BER、能量和信号链摘要、教学复盘。
- `frontend/src/AppShell.tsx`、`frontend/src/Router.tsx`：在现有导航注册 Stage10 路由。

未修改 `backend/convolutional_coding.py`、`backend/tests/oracles/stage10_convolutional_oracle.py`、Stage01–Stage09 页面或既有 API 行为。

## API 与数据链路

`POST /api/stage10/experiments` 接受 `n_information_bits`（1–4096，默认 256）、`eb_n0_db`（−10 至 30 dB，默认 4）、`seed`（0 至 2³²−1，默认 2026）及 `include_details`。未知字段、非法数值、非整数计数/种子，以及超过 256 位的完整细节请求被拒绝；异常响应不包含内部堆栈。实验无 ID、缓存或持久化，响应即完整结果。

路由直接调用 Phase 2 `run_experiment`，返回实际固定码参数、随机种子、长度、噪声方差/标准差、三个 BER、尾位、译码恢复标志、教学文本和有限细节。默认返回最多 64 个信息位及对应前 128 个码位的预览；完整细节模式限 256 信息位。接收实值样本最多展示前 24 个供教学观察。

数学口径保持 K=3、(7,5)、R=1/2、`(g0,g1)`、两个零尾位、终止式硬判决 Viterbi。信息位 Eb=1 时，编码符号能量为 `R*Eb=0.5`，两条链路使用相同信息位 Eb/N₀ 和 `N0=Eb/10^(Eb/N0_dB/10)`；噪声方差为 `N0/2`。未编码和译码后信息 BER 的分母为 N；编码接收 BER 按全部编码位（含尾位）统计。页面明确展示三种 BER 的分母差异，且单次实验教学结论来自实际误码结果。

## 测试与实测

- Stage10 API + Phase 2 生产核心 + Phase 1 数学 Oracle：**41 passed**，0 warnings。
- Stage01–Stage09 回归（全体原有后端测试，不含新增/既有 Stage10 测试）：**549 passed，5 warnings**。警告为既有 NumPy 溢出边界用例及 httpx 测试内容弃用提示。
- 完整后端套件：两组覆盖合计 **590 passed**。其中首次整套运行在新增 API 测试内容参数调整前报告 6 条警告；最终分组运行新增 API 测试无警告，Stage01–09 仍有上述 5 条警告。
- `npm run lint`：通过。
- `npm run build`：TypeScript 项目构建与 Vite 生产构建通过。
- `git diff --check`：通过；仅有 Windows CRLF 转换提示，不是空白错误。
- 浏览器实测：本地 Vite + FastAPI 中打开 `#/stage10`，运行默认 seed 2026 实验，页面显示 BER `4/256`、`31/516`、`1/256`，编码符号能量 0.5、噪声方差约 0.1991、尾位 `[0,0]`、64 信息位/128 码位的有限预览与真实接收样本；切换到完整细节且设 257 位时出现明确错误提示并保留输入；通过公共导航返回 `#/` 的 Stage01 成功。页面实测截图显示导航、参数表单及 BER 区块；没有进行物理设备或多视口矩阵测试。

Impeccable 启动器的 `critique` 和 `audit` 命令在本环境返回 `Unknown command`，因此工具化 critique/audit 未完成；已按已有项目 Token 和 Stage08/09 模式实施，并对浏览器渲染与主要交互作人工检查。`i-have-adhd` 未安装。此为工具限制，不影响构建和功能测试结果。

## 已知限制

- 页面仅呈现单次实验和有限码字预览；不提供性能曲线批量仿真、软判决或可配置码族。
- 实验是无状态请求，刷新不会恢复实验历史。
- 页面实际检查使用当前默认浏览器视口，未覆盖独立 375/768/1440 视口或物理设备触控。

## Git 交付

- 实现提交：`280faeff5dabf106244b24018bbeed32f13aa100`（`Add Stage10 coding experiment API and lab`）。
- Author：`DemaciaForge <DemaciaForge@users.noreply.github.com>`。
- Committer：`DemaciaForge <DemaciaForge@users.noreply.github.com>`。
- 提交前重新 fetch 后，`origin/main` 仍为 `338496d45f8af858f8f3a84640f3479145c7521d`；本地提交是其普通快进后继。推送及推送后核验结果将在实际执行后记录。
