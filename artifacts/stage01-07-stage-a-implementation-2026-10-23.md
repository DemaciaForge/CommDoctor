# CommDoctor Stage01–Stage07 Stage A 核心体验实施与验收

日期：2026-10-23（Asia/Shanghai）
项目：`D:\CommDoctor\projects\CommDoctor-main`
目标远端：`https://github.com/DemaciaForge/CommDoctor`，分支 `main`

## 1. Git 与工作区基线

- 当前分支：`main`。
- 本轮开始 HEAD：`c55e193026d399c61fad74408118be57cf8e5450`。
- 本轮开始 `origin/main`：同一 SHA；完成验收前 `git fetch origin main` 后仍相同，无远端新提交。
- 工作区原有未跟踪文件：`.agents/`、`.codex/`、`AGENTS.md`、`artifacts/stage01-07-uiux-audit-2026-10-23.md`、`artifacts/stage02-p2-round15-browser-acceptance.md`。均予以保留，不纳入本轮提交。
- 本轮修改：`frontend/index.html`；`frontend/src/App.tsx`、`DiagnosticChallengeApp.tsx`、`FaultDiagnosisApp.tsx`、`FrequencyOffsetApp.tsx`、`MultiFaultApp.tsx`、`PhaseOffsetApp.tsx`、`Router.tsx`、`TripleFaultApp.tsx`、`index.css`；新增 `AppShell.css`、`AppShell.tsx`、`api.ts`。
- 后端、算法、测试、API endpoint 和实验参数契约未修改。

## 2. Skills 与辅助检查

已读取 `AGENTS.md`、阶段审计报告、`.agents/skills/i-have-adhd/SKILL.md`、`.agents/skills/ui-ux-pro-max/SKILL.md`、`.agents/skills/impeccable/SKILL.md`。Impeccable 的 `reference/craft-floor.md` 在此次 UI 编辑继续前读取。

- i-have-adhd：采用有限步骤和清晰验收点，先核实工作区、做实现、再浏览器验收与交付检查。
- UI UX Pro Max：沿用先前设计基线（通信教学实验室、图表优先、色彩传达信号、术语有解释、键盘和窄屏可用）；本轮未引入新设计体系。
- Impeccable 实际命令：
  - `.agents/skills/impeccable/scripts/impeccable.cmd context`
  - `.agents/skills/impeccable/scripts/impeccable.cmd detect --json frontend\src`
  - `.agents/skills/impeccable/scripts/impeccable.cmd audit frontend\src`
  - `.agents/skills/impeccable/scripts/impeccable.cmd critique frontend\src`
- 当前 CLI 的 `context`、`detect` 可用；`audit` 与 `critique` 均返回 `Unknown command`。按实际安装版本以 detector 作辅助，不将不可运行的命令记为通过。
- detector 唯一 warning：既有 `frontend/src/FaultDiagnosis.css:437` side-tab 左侧色条（P2 视觉一致性）；本轮保留，没有顺手修改。

## 3. 实施结果

- 新增共享 `AppShell` 和导航，七个 Hash 路由展示当前阶段，并有统一实验阶段说明；保留既有路由和页面内容。
- 新增 `api.ts`，通过 `VITE_API_BASE_URL` 注入后端基址，默认沿用现有后端 `http://127.0.0.1:8000`；去除尾部斜杠，所有页面共用请求和友好错误处理。源码搜索仅发现集中在 `api.ts` 的默认地址。
- 页面 `lang`/`title` 改为中文产品身份；补充全局 `:focus-visible`、禁用按钮、状态/错误语义和 `prefers-reduced-motion`；为 Stage02 DC 开关增加标签/状态说明，并扩展少量影响理解的 BER、DC、门限术语提示。
- Stage07 只增加现有模型术语解释，没有改动八种场景、诊断路径或补偿行为。

## 4. 浏览器验收矩阵

使用 Codex In-app Browser 的真实页面和 Playwright DOM/视口能力；浏览器地址 `http://localhost:5173/`，后端 `127.0.0.1:8000`。逐页检查了当前阶段标识、标题、可见核心操作、横向滚动宽度；各页浏览器控制台 error/warn 为空。宽度：375×812、768×900、1440×1000。三种宽度均覆盖七个路由。`375px` 的 Chromium 实际页面/文档宽度为 360px（浏览器可用区域），没有超出页面宽度；`768/1440` 下也无横向溢出。

| Stage | 375/768/1440 加载和导航 | 本轮核心操作与结果 |
|---|---|---|
| 01 | 通过；当前标识正确，无横向溢出 | 点击仿真；10,000 bits、Eb/N₀ 8 dB、2 errors，理论 BER `1.9091e-4`、实测 `2.0000e-4`；图示渲染。 |
| 02 | 通过；当前标识正确，无横向溢出 | 打开 DC 故障注入并运行诊断；识别均值 `0.7868`，建议门限 `0.7868`；点击应用建议门限，BER 从 `0.123` 降到 `0.0002`（2 errors）。 |
| 03 | 通过；当前标识正确，无横向溢出 | 开始挑战、均值测量 `0.7979`、正确判断 DC 故障、运行门限修复；BER 从 `0.1191` 降至 `0.0002`，出现挑战复盘。 |
| 04 | 通过；当前标识正确，无横向溢出 | 创建对照实验、估计频偏 `0.000000 cycles/symbol`；先提交与证据不符判断得到可重试提示，再选正常对照诊断成功并执行补偿。 |
| 05 | 通过；当前标识正确，无横向溢出 | 创建随机实验并测量；提交证据支持的“仅频率偏移”正确；执行仅频偏补偿。 |
| 06 | 通过；当前标识正确，无横向溢出 | 创建正相位挑战，估计 `44.8485°`，正确诊断相位故障，使用估计角度执行补偿复盘。 |
| 07 | 通过；当前标识正确，无横向溢出 | 创建随机挑战，测量 DC/频偏/相位，正确诊断三重故障并联合补偿；BER 从 `0.5002` 降至 `0.0002441`，渲染参数估计误差与教学复盘。 |

- 导航验证：从首页切换到 Stage02，刷新仍在 Stage02；浏览器后退回首页、前进回 Stage02。
- API 不可用验证：停止本轮后端后在 Stage01 点击仿真，页面显示“无法连接实验服务。请确认后端已启动，然后重试。”，控制台无 error/warn；随后恢复后端完成 Stage03/02 的主流程。
- 配置验证：`VITE_API_BASE_URL=http://localhost:8000/` 执行生产构建成功，设置了带尾斜杠的基址仍生成正确应用包；本地真实请求成功。默认值集中在 `api.ts`。
- Stage01–07 路由覆盖 7/7（100%）；每页完成实际核心操作至少一条。本轮没有穷举随机场景和全部错误路径。

## 5. 自动化检查

- 前端：`npm run lint`，退出码 0。
- 前端 TypeScript + 生产构建：`npm run build`（内含 `tsc -b`），退出码 0；Vite 转换 33 modules，JS gzip 82.78 kB。
- 带显式 `VITE_API_BASE_URL` 的第二次 `npm run build`，退出码 0。
- 后端：`python -m pytest -q`，退出码 0，`518 passed`；5 条已有数值/依赖警告（3 条 NumPy overflow 预期边界用例，2 条 httpx 内容参数弃用）。本轮没有更改后端业务。
- `git diff --check`：通过；只有 Git 对 LF/CRLF 的提示，没有空白错误。

## 6. 未解决事项与优先级

- P1 未发现。核心流程、路由刷新、历史导航和错误恢复提示在本轮实际通过。
- P2：现有 FaultDiagnosis side-tab 左边框 detector 警告；Stage01/02 页脚仍显示“AI辅助开发 (Claude Code)”内部元信息，影响产品面向学生的身份感，建议在后续一致性阶段单独评估；未将其作为功能阻断。
- 尚未做 NVDA 等读屏、200% 缩放、真实触屏硬件和全部随机组合穷举。当前浏览器视口截图和 DOM 检查不替代这些验证。

## 7. GitHub 提交状态

功能提交：`24a177e54ee81ec9a5d23a3862aca871200b56b9`（Improve core Stage01-07 experience）。Author 与 Committer 均为 `DemaciaForge <DemaciaForge@users.noreply.github.com>`，无 Claude 联合作者。功能提交仅含上述 13 个前端文件；验收报告独立提交为 `ff8d8530e97a249a2688313462a02b8b8a9f92d9`，行尾空白修订为 `29e4114a2ddb7f38cf6f6c48d58f55f517f25fe5`。`git push origin main` 已成功推送至指定仓库，随后 fetch 确认本地 HEAD 与 `origin/main` 同为 `29e4114a2ddb7f38cf6f6c48d58f55f517f25fe5`。

## 8. 服务和工作区收尾

- 前端 dev server：本轮进程 `node` PID `33856`（父进程 PID `34084`），`localhost:5173`；最后停止并确认无本轮监听。
- 后端首次实例 PID `33704` 在 API 故障提示测试中停止；为恢复后续测试重启，进程记录 PID `42960`。本轮后端 PID `42960` 已于交付前停止，确认 `8000` 端口无 LISTENING 进程。前端 dev server PID `33856`（父进程 `34084`）已停止，确认 `5173` 端口无 LISTENING 进程。
- 原有未跟踪文件全部保留；既有审计报告未覆盖；生成文件只包括本报告和构建输出目录（dist 由 ignore 规则处理）。
