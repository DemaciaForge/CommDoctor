# Stage11 Phase 3 API 与交互式实验室验收

日期：2026-10-27

项目：`D:\CommDoctor\projects\CommDoctor-main`

起始分支与 HEAD：`main` / `24b733ac312d97c773bc14fa1265194fb344c389`

起始 `origin/main` 与 GitHub 实时 `main`：`24b733ac312d97c773bc14fa1265194fb344c389`

## 交付内容

- 新增 `POST /api/stage11/experiments`。复用 Stage10 `encode_frame`/`decode_frame` 和 Phase 2 `interleave_bits`/`apply_burst_errors`/`deinterleave_bits`，返回真实输入、各阶段位序列、矩阵排列、传输错误索引到编码索引映射、译码错误索引与 BER 统计。
- 单帧约束为信息位 1–4096、矩阵单轴 1–4096、矩阵最多 1,048,576 位，严格校验传输区间、种子和额外字段。响应错误沿用 FastAPI 校验格式；未预期错误使用不泄露堆栈的 500 信息。
- 信息 BER 使用信息位错误数除以原始信息位数。尾位和交织填充位不会进入信息 BER 分母；填充位可被传输突发翻转，但不会计入有效编码错误统计。
- 新增 `#/stage11` 页面并接入共享 `AppShell`、导航、`apiRequest`、`ChartFrame` 与 `MetricGrid`。页面显示流程、长度摘要、映射与位序列、错误统计和基于本次真实响应的复盘；长序列使用局部窗口并说明窗口范围。
- 按项目要求阅读并使用 `i-have-adhd`、`ui-ux-pro-max`、Impeccable 相关 Skill 说明。Impeccable context/detector 可执行；安装版本不支持要求中提及的 `audit`/`critique` 命令，因此未运行这两项。

## 文件

- 修改：`backend/main.py`、`frontend/src/AppShell.tsx`、`frontend/src/Router.tsx`。
- 新增：`backend/test_stage11_api.py`、`frontend/src/Stage11InterleavingApp.tsx`、`frontend/src/Stage11Interleaving.css`、本报告。
- 开始工作时已存在的未跟踪材料（Phase 1 Oracle、先前报告、设计系统和其他测试等）均保留，没有纳入本次交付提交。

## 自动化验证

- Stage11/Stage10 定向基线：45 passed（变更前）。
- Stage11 专项及 Stage10 定向测试：121 passed（本次实现后）。
- 完整后端：`python -m pytest -q` → **676 passed**，5 warnings，4.39s。警告均来自既有溢出边界测试与 httpx 测试 API 弃用提示；本轮未修改这些范围外行为。
- 前端：`npm run lint` 通过；`npm run build` 通过（包含 `tsc -b` TypeScript 检查和 Vite 生产构建）。没有配置独立前端自动化测试脚本。
- `git diff --check` 通过。
- Stage11 API 专项覆盖生产算法精确复算、合法输入、最小输入、突发填充位、行列/长度/索引/种子/额外字段约束、响应错误隐藏和 BER 分母。

## 浏览器验收

浏览器：REA 控制的 Chromium 156（Edge 可执行文件），本地 Vite 前端和 Uvicorn API。

- **1440×1000**：打开 `#/stage11` 并运行默认参数；捕获 Stage11 POST，响应 200，检查实际 JSON 中 64 信息位、132 有效编码位、144 传输位、12 填充位、突发映射、2/64 信息 BER 和真实阶段位序列。页面由共享 Shell 导航承载。
- **768×900**：修改信息位数后提交越界突发起点，页面显示“突发区间必须完整位于传输帧内”的可理解错误；纠正起点后重试，Stage11 POST 返回 200。无浏览器 page error 或控制台 error。
- **375×850**：从 Stage10 导航进入 Stage11，运行默认实验，执行 Tab 焦点移动和刷新操作；步骤均完成且刷新后路由仍为 `#/stage11`。
- **服务失败**：停止后端时在页面提交，显示“无法连接实验服务。请确认后端已启动，然后重试。”；重启服务后的独立浏览器场景成功提交并收到 200，证明可恢复重试。
- 页面可访问性快照显示有命名导航、Stage11 当前页标识、标题层级、标签化表单控件和 alert 错误区域。Tab 按键已执行，但场景采集器不提供可靠的当前焦点目标断言；焦点视觉状态未作独立验证。
- 从 Stage10 进入 Stage11 已验证。通过浏览器按键触发的历史后退/前进没有观察到路由变化，前进/后退专项未验证；Stage11 刷新已验证。
- 交织可视化、结果和教学复盘来自 API 输出；无错误控制台或页面异常。

## 未验证与遗留

- Stage10→Stage11 已完成，Stage11→Stage10 的点击往返和可靠的浏览器历史前进/后退行为未全部验证。
- 浏览器验收基于本地开发服务（Vite/uvicorn），不是部署环境验收。
- 没有独立组件测试脚本；功能行为由后端数据流精确测试及上述浏览器交互覆盖。
- Impeccable `audit`/`critique` 子命令在当前安装版本不可用；已执行可用的 context/detector 检查，没有基于 detector 提示扩大样式重构。
- 5 个既有后端运行时/弃用警告保留记录，不影响本次功能通过。

## Git 交付

本轮只提交本报告、`backend/main.py`、`backend/test_stage11_api.py`、`frontend/src/AppShell.tsx`、`frontend/src/Router.tsx`、`frontend/src/Stage11InterleavingApp.tsx` 和 `frontend/src/Stage11Interleaving.css`。其余起始未跟踪材料均保留。

- 功能提交：`a9191f2824e586c311ebe34a7347c448be812054`（`feat(stage11): add burst interleaving experiment lab`）。
- 报告整理提交：`917665ab8ebb9b65dd804c3bc43a409bacd8a414`（`docs(stage11): finalize phase 3 acceptance report`）、`54b2fc7ca960f2c5ffb64a99e0553c1c1d259bbe`（`docs(stage11): record verified main delivery`）。
- 两个提交作者和提交者均为 `DemaciaForge <DemaciaForge@users.noreply.github.com>`；核验提交头未包含其他署名。
- 已普通快进推送，无强推或历史改写。最终报告更正前再次 fetch 并查询 GitHub 实时 `main`：本地 HEAD、`origin/main` 和 GitHub `refs/heads/main` 均为 `54b2fc7ca960f2c5ffb64a99e0553c1c1d259bbe`。随后仅更新本报告的核验记录并将该更正作为独立提交推送。
- 推送后的 `git status --short` 仅列出任务开始前已存在的未跟踪材料；本轮代码与报告文件均已提交，工作区无本轮残留修改。
