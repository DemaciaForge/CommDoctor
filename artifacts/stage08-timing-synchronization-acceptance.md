# Stage08 符号定时偏移与采样同步验收报告

日期：2026-10-24
仓库：`D:\CommDoctor\projects\CommDoctor-main`
分支：`main`

## 交付内容

- 新增隔离的 RRC BPSK 过采样定时实验模块 `backend/timing_sync.py`。
- 在 `backend/main.py` 增加创建、波形观察、测量、诊断、采样相位补偿和复盘 API。
- 新增独立标量数学 oracle 与后端回归测试：`backend/test_stage08_timing_oracle.py`、`backend/test_stage08_timing_sync.py`。
- 新增 `#/stage08` 实验室页面并挂入共享路由和导航：`frontend/src/TimingSynchronizationApp.tsx`、`frontend/src/TimingSynchronization.css`、`frontend/src/Router.tsx`、`frontend/src/AppShell.tsx`。

## 物理与统计口径

采用固定 BPSK/RRC 链路，16 samples/symbol、滚降系数 0.35、跨度 8 Ts、Tx/Rx 各 129 taps。单级群延迟 64 samples，级联延迟 128 samples。正 q 表示接收波形延迟 q 个样本；训练序列有限网格上以 pilot MSE 选相位，候选为离散 samples。补偿前后复用同一接收数据，仅改变采样索引。BER 只统计固定 payload 区间，不含 pilot 和保护区。

## 自动化验证

- Stage08 专项数学 oracle 与 API 测试：19 passed（实施阶段专项结果）。
- 全量后端：537 passed，5 warnings。警告来自既有极值溢出/旧上传测试；无失败。
- 前端 `npm run lint`：通过。
- 前端 `npm run build`：通过（TypeScript 与 Vite production build）。
- `git diff --check`：通过；仅提示既有 Git 行尾转换提醒。
- 未增加依赖。

## 浏览器端到端验收

使用本机真实 Chromium 内嵌浏览器打开 `http://127.0.0.1:5174/#/stage08`，前端 API base 指向本轮本地后端 `127.0.0.1:8001`。流程实测：隐藏挑战创建成功；真实过采样波形与匹配滤波延迟显示；测量返回 15 个候选相位评分；提交错误诊断得到可恢复反馈；修正诊断后可补偿；最终复盘展示实际偏移与 BER。该轮随机实验估计偏移为 -3 samples，估计误差 0，补偿前 4/1024（BER 0.00390625），补偿后 0/1024。此为单次观察结果，不代表普遍改善保证。

后端 HTTP 日志确认各 API 请求均为 200（首次使用临时端口 5175 时 CORS 预检为 400；随后切换到项目允许的 5174 端口完成验收，未改源码 CORS 配置）。浏览器控制台没有 error/warn 条目。

响应式检查设置 viewport 为 375×812、768×1024 和 1440×1000。三种宽度的 document/body scrollWidth 均未超过当前布局宽度；375px 截图中导航、诊断选项、状态反馈和操作卡片可见，无横向溢出。键盘 Tab 导航到页面首个品牌链接，焦点轮廓为可见的 2.67px solid。图表以 SVG viewBox 缩放并保留标签及图例。

## 验收结论与限制

Stage08 MVP 的核心用户流程、数值对照、API 状态门控及桌面/平板/移动布局检查通过。定时估计仅是已知训练序列上的有限整数采样相位网格搜索，噪声下可能选错；本阶段不覆盖分数延迟、采样时钟漂移、多径、载波频率或相位偏移。响应式和交互在本地真实浏览器完成；未执行生产部署环境验收。

## Git 发布

实施前基线为 `main` / `origin/main`：`596faed2a234e096cae9459f015282b1155d2c42`。验收后将只暂存 Stage08 的 7 个生产/测试文件及本报告，保留先前未跟踪的 `.agents/`、`.codex/`、`AGENTS.md`、Stage01–07 报告及 Stage08 技术方案，不纳入提交。提交及推送结果在实施完成后补记。
