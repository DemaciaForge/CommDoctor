# CommDoctor Stage12 Phase 1：独立软判决 Viterbi Oracle 与契约测试

日期：2026-10-27（Asia/Shanghai）

仓库：`D:\CommDoctor\projects\CommDoctor-main`

分支：`main`

## 1. 初始状态与源码核查

本轮开始前实际核对：当前分支为 `main`；HEAD、`origin/main` 和 GitHub `refs/heads/main` 均为 `db3da5f69b99d8368aa89f17936962b309c963ca`。tracked 工作区 diff 与暂存区 diff 均为空。工作区已有 `.agents/`、`.codex/`、`AGENTS.md`、Stage01–Stage12 方案/验收材料、Stage10/11 Oracle 与测试、`design-system/` 等未跟踪项目；本轮不清理、不覆盖、不暂存这些文件。

开始前确认以下新增目标路径均不存在：

- `backend/tests/oracles/stage12_soft_viterbi_oracle.py`
- `backend/test_stage12_soft_viterbi_oracle.py`
- `artifacts/stage12-phase1-soft-viterbi-oracle.md`

实际读取 `AGENTS.md`、Stage12 正式方案、`backend/convolutional_coding.py`、Stage10 独立 Oracle/契约测试、Stage10 Phase 1/2/4 报告。当前生产实现事实如下：K=3、四状态、状态 `2*m1+m2`、八进制生成多项式 `(7,5)`、每拍输出 `(g0,g1)=(u xor m1 xor m2, u xor m2)`、R=1/2、payload 后追加两个零输入、初态和终态为 0；BPSK 为 `0→-A, 1→+A`，编码符号能量为 `R*Eb_info=0.5`，默认 `Eb_info=1`；实 AWGN 方差是 `N0/2 = 1/(2*10^(Eb/N0_dB/10))`。硬判决为 `sample > 0` 得 1、否则 0；现有硬 Viterbi 的 Hamming 分支度量在目标状态平局时选择数值较小前驱状态，最后约束零态、验证两个零尾并剥除尾位。

本轮没有修改这些生产事实。没有生产软判决 Viterbi；以下测试只能验证独立数学基准及现有硬判决关系，不能宣称 Phase 2 已实现。

## 2. 独立 Oracle 设计

新增 `backend/tests/oracles/stage12_soft_viterbi_oracle.py`。模块只依赖 Python 标准库 `dataclasses`、`math`、`typing`，没有导入 `convolutional_coding`、NumPy 或任何生产译码函数。它用独立标量寄存器方程生成候选编码帧，不复用生产状态递推或 survivor/traceback 动态规划。

对信息长度 N≥1，Oracle 枚举全部 `2^N` payload；每条候选追加 `(0,0)`，生成完整 `2*(N+2)` 码位，再按实际 Stage10 BPSK 幅度构造符号。给定同长度有限实接收样本 `y`，计算

`M(c) = Σ_i (y_i - A(2c_i-1))²`。

`optimal_paths` 返回所有达到最小距离的 `SoftPath`，包括 payload、完整编码输入、码字和距离。它不把数学平局强行压成唯一答案。空 payload 不属于当前 Stage10 合法契约，因此明确拒绝；短帧穷举不被用作长帧性能证明。

## 3. 度量推导与发射映射

Stage10 编码符号为 `s_i=A(2c_i-1)`，其中 `A=sqrt(R*Eb_info)=sqrt(0.5)`。AWGN 条件密度的负对数（去掉与候选路径无关的常数）为

`Σ_i (y_i-s_i)²/(2σ²)`。

同一次实验中 `σ²` 对所有合法候选相同，除以 `2σ²` 不改变 argmin；因此 Oracle 保存未归一化平方距离，生产实现将来可以使用该距离、除以固定因子后的距离，或证明等价的相关形式。绝对差和 Hamming 距离不属于该 AWGN 最大似然度量。

测试锁定了 `Eb_info=1`、编码能量 0.5、幅度 `sqrt(0.5)` 和 0 dB 方差 0.5，并验证缩放后路径排序不变。

## 4. 平局、尾位和终止

所有接收样本精确为 0 时，每个候选 BPSK 符号的平方距离都相同。N=1 的 Oracle 精确返回 payload `{(0,), (1,)}`，距离为 3.0；这是数学上真实的全局平局，不是浮点近似。

Oracle 只枚举 payload 后追加两个零尾输入的路径，故最优集合天然满足初态零、终态零和尾位 `(0,0)`。测试另构造三个输入 `(1,1,1)` 的非终止码路径：不约束终态时距离为 0，而终止候选的最小距离严格大于 0，证明终止约束不可省略。

本阶段对数学平局只要求生产未来输出属于 Oracle 最优集合。给 Phase 2 的建议是沿用 Stage10：同一目标状态出现完全相等的路径度量时选择数值较小前驱；新测试以局部候选负对照验证采用较大前驱会违反该建议。正式生产软 Viterbi 尚不存在，因此这只是规则级契约建议，尚未验证生产 survivor tie-break；Phase 2 开工时应冻结规则并对真实生产实现写定向测试。

## 5. 测试矩阵与实际结果

新增测试 `backend/test_stage12_soft_viterbi_oracle.py` 覆盖：

- Oracle AST 独立性、已知 `(1,0)` 码字、全零/全一/交替短帧和所有 N=1..6 无噪声路径。
- 独立平方距离证书、零样本精确平局、BPSK 正负幅度与输出顺序、两个零尾和终态。
- 相同接收样本上硬判决与软 Oracle 可得不同结果的明确案例；同时证明不能预设每个有限样本软判决都更优。
- 非终止路径、错误 Hamming 度量、交换输出顺序、遗漏尾位和逆转前驱 tie-break 等隔离变异负对照。
- NaN/±Inf 拒绝、`1e150` 有限距离、`1e308` 平方溢出拒绝、接收长度错误和最短帧校验。
- Stage10 `Eb/N0`、幅度、方差和信息 BER 分母/共同接收数组的公平比较辅助契约。

本轮实际运行命令均在 `D:\CommDoctor\projects\CommDoctor-main\backend` 执行，退出码均为 0：

| 检查 | 实际结果 |
|---|---|
| `python -m pytest -q test_stage12_soft_viterbi_oracle.py` | **15 passed** |
| `python -m pytest -q test_stage10_mathematical_oracle.py test_stage10_convolutional_coding.py` | **34 passed** |
| `python -m pytest -q test_stage10_api.py test_stage10_ber_sweep.py` | **13 passed** |
| `python -m pytest -q` | **691 passed, 5 warnings**，约 4.70 秒 |
| `git diff --check` 与新增文件空白检查 | **通过**，退出码 0 |

完整后端的 5 个 warning 均为既有 Stage01–Stage09 数值溢出运行时警告和 HTTPX raw content 弃用警告；没有新增生产源码，也没有为清理这些 warning 修改范围外文件。

## 6. 负对照与独立性边界

测试内的错误实现只存在于测试函数局部：用硬 Hamming 评分替代平方距离会在大幅样本案例中选出 payload 0，而软 Oracle 选 payload 1；交换 `(g0,g1)` 或只保留一个尾位会与锁定码字/长度不同；忽略终态会接受非终止零距离路径；平局时选择较大前驱与建议规则产生不同选择。没有修改生产源码，也没有生成需要清理的临时变异文件。

“硬、软使用不同接收样本”目前只能作为辅助契约测试由同一个 `received` tuple 传入；不存在 Stage12 生产配对函数可供直接审计。因此，固定 seed、单次噪声生成和生产 API 的同数组证据仍是 Phase 2/3 必测项。

## 7. 数值稳定性与性能限制

Oracle 的候选数量为 `2^N`，每个候选长度为 `2(N+2)`，时间复杂度约 `O(N·2^N)`，存储至少为候选结果数量及一条路径的 `O(2^N·N)`；它只适合短帧数学证书。有限输入的平方也可能溢出：本 Oracle 对 `1e308` 明确抛出距离溢出错误，而不是把 `inf` 当作合法比较结果。`1e150` 仍在本机双精度可表示范围内并被测试。

未来生产四状态 Viterbi 每个时刻只有 4 个状态、每状态 2 条分支，时间复杂度为 `O(8·(N+2))=O(N)`；若保存每时刻每目标状态的前驱和输入决定，回溯存储为 `O(4·(N+2))`，可选完整 metric 轨迹同阶。Phase 2 必须实测长帧、极端有限样本、平方/相关等价形式、每时刻减最小 metric 的归一化，以及 API 预算/超时；本轮没有把 Oracle 时间当作生产性能，也没有运行大规模基准。

## 8. 进入 Phase 2 的判定

本轮新增 Oracle 和测试满足进入 Phase 2 的数学前置方向：Oracle 独立、度量与 Stage10 发射映射一致、短帧最优路径/平局/尾位/终态和关键变异均有明确断言；专项、Stage10 定向和完整后端测试均通过。因此可以进入 Phase 2 的生产实现准备，但 Phase 2 开始时必须先冻结软 Viterbi 的确定性 tie-break（建议固定状态/分支遍历顺序，并在目标状态度量相等时选择数值较小前驱），再实现生产函数。当前尚未验证该规则在软生产译码器中的实际执行。

无论专项测试是否通过，以下仍是 Phase 2 必须完成的项目：生产软输入 Viterbi、确定性软路径 tie-break、长帧数值归一化和溢出策略、同一个接收数组的硬软配对、固定 seed 的生产重放、真实 BER 统计及性能预算。本轮没有实现生产软判决译码器，也没有启动 Phase 2。

## Git 最终状态

本轮只新增上述三个文件；未执行 `git add`、提交、推送、reset、restore、checkout、rebase 或清理。结束时 HEAD/分支、`origin/main` 与 GitHub `main` 仍为 `db3da5f69b99d8368aa89f17936962b309c963ca`；暂存区为空；工作区仅增加上述三个未跟踪文件，既有未跟踪材料仍保留。
