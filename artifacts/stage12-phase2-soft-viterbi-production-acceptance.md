# CommDoctor Stage12 Phase 2：生产级软判决 Viterbi 译码器验收

日期：2026-10-27（Asia/Shanghai）
仓库：`D:\CommDoctor\projects\CommDoctor-main`
分支：`main`

## 范围与基线

本轮实现 Stage12 Phase 2 生产软输入 Viterbi 核心及必要测试。没有实现 Stage12 API、前端页面或 BER 扫描，也没有修改 Phase 1 Oracle、既有 API、配置、依赖或硬判决算法。

执行前核对结果：HEAD 与 `origin/main` 均为 `db3da5f69b99d8368aa89f17936962b309c963ca`，GitHub 实时 `refs/heads/main` 同一 SHA；远程为 `https://github.com/DemaciaForge/CommDoctor.git`。工作区原有大量未跟踪 Stage 报告、Oracle、测试和 `design-system/`，均保留。本轮新增目标报告在执行前不存在。

## 生产实现

- `backend/stage12_soft_viterbi.py`：新增 `soft_viterbi_decode`、`SoftDecodeResult`、`paired_decode` 和 `PairedDecodeResult`。
- `backend/convolutional_coding.py`：新增公开入口 `soft_viterbi_decode` 和 `paired_decode`，通过延迟导入接入 Stage12 核心；既有 `decode_frame`、`viterbi_decode`、编码器和硬判决路径未改变。
- `backend/test_stage12_soft_viterbi.py`：新增生产专项测试。

译码器复用现有 `transition`，固定零态起始、零态终止、(7,5) 四状态 trellis、两个零尾位及 `(g0,g1)` 输出顺序。它直接消费实数接收样本，未先硬量化。

软分支度量是 AWGN 最大似然平方欧氏距离。为避免有限极端样本的单项平方溢出，实现把整帧的接收样本和发射幅度同时除以同一个正数 `scale=max(A,max|y|)`，再累加缩放后的平方距离；这只把所有候选路径乘以同一个正因子，不改变 argmin。每个时刻从所有有限 survivor metric 中减去最小值，保留相对路径排序；结果中的 `path_metric` 因此是归一化后的相对 metric，`metric_scale` 记录全帧缩放因子。`NaN`、无穷、错误长度、空帧、布尔和字符串样本均拒绝。

同一目标状态的候选 metric 使用严格 `<`；仅在 `==` 时选择数值较小的前驱状态。状态和分支遍历顺序固定，回溯验证初态、终态和尾位后才剔除两个尾输入。`paired_decode` 先把输入样本作为一个已校验序列，再对同一数据执行 `hard_decision` + 既有硬 Viterbi 与软 Viterbi，统计分母恒为信息位数。

## 测试与性能

本轮实际执行，均在 `backend` 目录，退出码为 0：

| 检查 | 实际结果 |
|---|---:|
| `python -m pytest -q test_stage12_soft_viterbi.py` | 19 passed |
| `python -m pytest -q test_stage12_soft_viterbi_oracle.py` | 15 passed |
| `python -m pytest -q test_stage10_mathematical_oracle.py test_stage10_convolutional_coding.py` | 34 passed |
| `python -m pytest -q test_stage10_api.py test_stage10_ber_sweep.py` | 13 passed |
| `python -m pytest -q` | 710 passed, 5 warnings |
| `git diff --check` | 通过 |

专项测试覆盖独立 Oracle 短帧最优性、零噪声全零/全一/交替帧、硬软同样本差异、确定性平局、尾位和终态、输入拒绝、极端有限值以及长帧恢复。Phase 1 Oracle 测试继续包含反向映射、错误度量、尾位、非终止路径和较大前驱平局等变异负对照；本轮未修改这些测试。

单独性能检查使用确定性 payload 和零噪声样本：信息位 1,024 / 8,192 / 32,768 时分别约 0.005450 / 0.044180 / 0.179425 秒，均完整恢复 payload，说明本实现按 trellis 时刻线性增长；未进行无界压力测试。完整回归中的 5 个 warning 来自既有 Stage01–09 数值溢出测试和 HTTPX raw content 弃用提示，本轮没有新增 warning 修复范围。

## 交付边界

本报告记录的验收基线仍为 `db3da5f69b99d8368aa89f17936962b309c963ca`。仅在本报告所有生产专项、Oracle、Stage10 回归和完整后端测试通过后，才按任务授权提交本轮 Stage12 文件；提交 SHA、author/committer 与推送后的远端状态在最终交付中报告。未使用 `git add -A`，未清理无关文件或改写历史。后续 Phase 3 可在此核心上实现有界 API、`#/stage12` 页面和配对 BER 扫描；这些内容不属于本轮验收。
