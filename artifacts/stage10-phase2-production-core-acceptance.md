# CommDoctor Stage10 Phase 2 生产核心验收报告

日期：2026-10-25（Asia/Shanghai）
仓库：`D:\CommDoctor\projects\CommDoctor-main`
分支：`main`

## 范围与初始状态

本轮实现固定 K=3、生成多项式 `(7,5)`（八进制）、母码率 `R=1/2` 的卷积编码、终止式硬判决 Viterbi、BPSK/AWGN 和 BER 统计。未修改 Stage01–Stage09、FastAPI 路由或前端。

开始时本地 `HEAD` 和 `origin/main` 均为 `6cd682d1ffc15128c75a282d3facbf711bc8714a`，当前分支为 `main`。tracked 工作区和暂存区均为空。`.agents/`、`.codex/`、`AGENTS.md`、Stage01–09 报告、Stage10 Phase 1 Oracle 及其测试等原有未跟踪文件均保留，未纳入本轮提交。

## 实际新增文件

- `backend/convolutional_coding.py`：固定参数生产编码、四状态 trellis、终止式硬判决 Viterbi、BPSK 硬判决、AWGN 量、BER 和可复现实验结果。
- `backend/test_stage10_convolutional_coding.py`：生产模块专项测试。
- `artifacts/stage10-phase2-production-core-acceptance.md`：本报告。

`backend/tests/oracles/stage10_convolutional_oracle.py` 和 `backend/test_stage10_mathematical_oracle.py` 未修改，继续作为独立 Phase 1 参考；它们是本轮开始前已存在的未跟踪文件。

## 算法与统计口径

编码器从 state 0 开始，状态为 `2*m1+m2`，每个输入位输出 `(u xor m1 xor m2, u xor m2)`，输出顺序为 `(g0,g1)`；payload 后固定追加两个零尾位，输出长度为 `2*(N+2)`，并验证终态回到 0。

Viterbi 对每个目标状态累积 Hamming 分支度量，只保留最优前驱；路径度量相等时选择较小前驱状态。初态和终态均固定为 0，完整回溯后剔除两个尾位，只返回 N 个信息位。生产译码没有穷举信息序列。

未编码 BPSK 符号幅度为 `sqrt(Eb)`；编码符号幅度为 `sqrt(R*Eb)`。默认 `Eb=1`，因此 `R=0.5`、编码符号能量为 `0.5`。两条链路使用相同信息位 `Eb/N0` 和 `N0=Eb/10^(Eb/N0_dB/10)`，实噪声方差为 `N0/2`。未编码 BER 分母为 N，编码通道 BER 分母为全部 `2*(N+2)` 个码位，译码后信息 BER 分母为 N，尾位不进入信息 BER。

`run_experiment` 使用 `numpy.random.SeedSequence(seed).spawn(3)` 派生信息位、未编码噪声和编码噪声三个固定域。相同输入、参数和 seed 返回完全相同的比特、接收样本、判决和统计结果；两条链路使用长度匹配且相互独立的噪声流。

## 验证结果

- Stage10 生产专项测试 + Phase 1 Oracle：**34 passed**。
- Stage01/08/09 定向回归（BPSK、Stage08 timing、Stage09 multipath）：**46 passed**。
- 完整后端测试：**583 passed, 5 warnings**。
- `git diff --check`：通过。

完整回归中的 5 个 warning 为既有 Stage01–Stage09 数值溢出和 httpx deprecation warning，未由本轮生产模块产生，也未阻断核心验收。

专项测试覆盖手工码字、全零/单 1/连续 1/交替输入、多种长度、无噪声全短序列、Oracle 最优路径集合、平局处理、尾位剔除、BER 分母、Eb/N0/码率/方差关系、seed 重放、极短帧及非法输入。

## 已知限制与待办

本轮只交付后端核心模块，没有新增 Stage10 FastAPI endpoint、前端 `#/stage10` 页面、流式译码、软判决 Viterbi、可配置码率或数据库持久化。这些属于后续集成工作；当前模块可由后续 API 直接调用，`ExperimentResult.to_dict()` 提供 JSON 友好的结果结构。

## Git 交付

核心实现与测试提交及报告最终化提交均使用以下指定身份。远端 `main` 已推送并核验到最终提交：

- 核心实现提交：`48c8a91757042e350a344ec31696faabf405c0e2`
- 验收报告最终化提交：见最终 Git 交付记录
- Author：`DemaciaForge <DemaciaForge@users.noreply.github.com>`
- Committer：`DemaciaForge <DemaciaForge@users.noreply.github.com>`
- 远端 `main`：已推送，稍后核验最终 HEAD
