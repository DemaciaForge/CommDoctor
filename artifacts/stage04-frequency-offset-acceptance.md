# Stage04 频率偏移诊断与补偿 MVP 验收

## 版本与范围

- 仓库：`D:\CommDoctor\projects\CommDoctor-main`
- 分支：`main`
- 开发前 HEAD：`87b467a1dadc5c8053c02a288545bc432373845e`
- Stage01/02/03 页面、路由和 API 保持原契约；Stage04 独立使用 `#/stage04` 和 `/api/stage04/...`。
- Stage01–03 未发现本轮必须处理的问题；未改动既有标准误差舍入算法。

## 模型与算法

发射符号为单位能量 BPSK，`a[n] ∈ {-1,+1}`，初相位固定为 0。接收模型为 `r[n] = a[n] exp(j 2π ε n) + w[n]`，其中 `ε = Δf·Ts`，单位 `cycles/symbol`。没有采样率/符号率，不声称 Hz。每个复 AWGN I/Q 分量方差为 `N0/2 = 1/(2·Eb/N0)`；8 dB 下相干 BPSK 理论 BER 为 `1.90907774e-4`。

频偏测量对 BPSK 接收样本平方，消去数据符号并将频率变为 `2ε`，用 16 倍零填充 FFT 的谱峰确定平方信号频率，再折半。理论无歧义范围为 `|ε| < 0.25 cycles/symbol`。固定种子的试验与在线验收验证正负符号、量级及补偿方向。死区 `±0.002` 仅用于解释正常对照的估计噪声；诊断判定由后端隐藏真实状态评价。

补偿按 `r_c[n] = r[n] exp(-j 2π ε_hat n)` 对原接收样本旋转，再对同一发送比特和同一噪声生成的样本作硬判决。每轮不重采样。

## API 与页面

- `POST /api/stage04/challenges`：创建 4096 符号挑战，返回实测信号子样本、理论/当前 BER 与图形数据；不返回真实 epsilon、标签、答案、种子或参考 BER。
- `GET /api/stage04/challenges/{id}/estimate`：返回平方信号频谱测得的归一化频偏。
- `POST /api/stage04/challenges/diagnosis`：后端评价用户的 `frequency_offset` / `no_offset` 判断；错误时不泄露答案且允许重试。
- `POST /api/stage04/challenges/compensate`：校验有限数值和严格范围 `(-0.25, 0.25)`，返回相同样本补偿前后误码和 BER。
- `GET /api/stage04/challenges/{id}/feedback`：只有诊断正确并执行补偿后才返回真实故障、参数、误差、结果、机理和局限。
- 页面提供 I/Q、星座、解调相位轨迹、测量、诊断、补偿和教学复盘；请求异常会显示错误。挑战状态为内存态。

## 验收结果

- Stage04 专项：`16 passed`。
- 后端全量：`431 passed, 5 warnings`。5 条为既有溢出/HTTPX 弃用警告，未影响通过。
- 前端：`npm run build`（含 `tsc -b` 与 Vite 生产构建）通过；`npm run lint` 通过。
- `git diff --check` 通过。
- 浏览器 `http://127.0.0.1:5173/#/stage04` 实测 I/Q、星座和相位图真实渲染，并完成以下流程：
  - 正常对照：估计 `0.000000`，诊断正确；零补偿前后均为 `0/4096`，BER `0`。理论 BER 为 `1.909e-4`，有限样本出现零误码属统计波动。
  - 正频偏：真实值 `+0.0200`，估计 `+0.020004`，诊断正确；误码 `2092/4096` (`BER=0.5107`) 降至 `1/4096` (`BER=2.441e-4`)。
  - 负频偏：真实值 `-0.0200`，估计 `-0.019997`，诊断正确；误码 `2038/4096` (`BER=0.4976`) 降至 `2/4096` (`BER=4.883e-4`)。
  - 错误判断返回不泄露答案的提示，之后可重选并诊断成功。
- API 测试验证创建响应不含隐藏字段，估计端不返回真实值；步骤门控、非法补偿、故障种类和反馈闭环均通过。

## 已知事项与优先级

- P0：无。
- P1：无未解决项。
- P2：挑战仅内存存储，页面刷新后需重开；估计采用谱峰 FFT，受包长、噪声和频偏靠近无歧义边界影响；暂只支持单一符号速率下的 BPSK 单载波频偏。
- P3：后续可增加相位误差/残余频偏可视化细节与无障碍图形描述，不影响本次闭环。

## Git 交付

- 本报告编写时尚未提交或推送。
- 计划只暂存本轮 Stage04 生产代码、测试和本报告；保留已有未跟踪文件 `artifacts/stage02-p2-round15-browser-acceptance.md`，不纳入提交。
- 提交身份按要求设置为 `DemaciaForge <DemaciaForge@users.noreply.github.com>`；提交 SHA 与推送/远端核验结果将在提交后更新本节。
- Stage04 功能提交：`0707a06a40bd43c5d9bce10ee2787122b6226edb`，Author/Committer 均为 `DemaciaForge <DemaciaForge@users.noreply.github.com>`。
- `git push origin main` 成功；推送后 `git ls-remote origin refs/heads/main` 与本地 HEAD 均为 `0707a06a40bd43c5d9bce10ee2787122b6226edb`。
- 验收报告随后单独更新并提交；原有未跟踪 `artifacts/stage02-p2-round15-browser-acceptance.md` 保持未跟踪、未暂存。
