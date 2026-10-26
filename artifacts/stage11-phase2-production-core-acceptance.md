# CommDoctor Stage11 Phase 2：生产交织器与突发信道验收

日期：2026-10-26（Asia/Shanghai）
仓库：`D:\CommDoctor\projects\CommDoctor-main`
分支：`main`

## 基线与范围

开始前确认本地 HEAD、`origin/main` 和 GitHub 实时 `main` 均为 `378e065e6a2b20499ae700b07bb336418f71cf71`，提交作者及提交者为 `DemaciaForge <DemaciaForge@users.noreply.github.com>`。开发前工作树存在 `.agents/`、`.codex/`、`AGENTS.md`、Stage01–10 报告及 Stage10/11 Oracle 和测试等多个未跟踪材料；本轮保留它们，不纳入提交。

本轮新增且仅新增以下交付文件：

- `backend/interleaving.py`：生产交织、反交织及确定性突发信道。
- `backend/test_stage11_interleaving.py`：Phase 2 专项及集成测试。
- `artifacts/stage11-phase2-production-core-acceptance.md`：本报告。

没有修改 Stage01–Stage10 生产文件、既有测试、Oracle、API、前端或依赖。

## 生产契约

`interleave_bits(values, rows, columns)` 将每个 `rows × columns` 块按行优先写入、按列优先读取；多块依次串接。末块以零补齐。不可变返回值 `InterleavedBits` 包含物理传输 `bits`、`valid_length`、`padded_length`、`pad_count` 和逐个传输位置的 `output_sources`；有效位来源为交织前索引，填充位来源为 `None`。`deinterleave_bits` 要求提供准确有效长度和完整填充块，只逆排列并返回有效序列。空输入返回空序列。

输入拒绝布尔值、非整数/非二进制值、非一维 NumPy 数组、非法维度、长度不符和超限输入。轴最大为 4096、块最大 1,048,576 位、序列最大 4,194,304 位。返回 tuple，且不修改调用者输入。

`apply_burst_errors(values, length, start=...)` 在实际传输序列索引 `[start, start+length)` 翻转连续比特。突发不得越过单帧边界；零长度合法，末尾零长突发也合法。指定 `start=None, seed=N` 时由局部 `random.Random` 选择合法起点，可重放且不读取/改变全局随机状态。返回 `BurstResult`，明确记录结果 bits、实际起点、请求长度、实际翻转位置/数量和传输有效长度。无交织路径中有效传输长度等于编码字长度；有交织时码字填充进入物理传输，但反交织后只把原始有效编码长度交给译码器。

测试通过 Phase 1 独立来源表核对传输错误位置到编码序列错误位置的映射。信道翻转数、反交织后的编码错误数和 Viterbi 信息错误数分别处理；译码信息分母为原始 payload 长度 N，尾位与填充均不进入该分母。测试不假设交织一定改善 BER。

## Stage10 集成

最小对照复用现有 `convolutional_coding.encode`、`viterbi_decode` 和 `decode_frame`。输入 payload 相同；Stage10 原有 K=3、(7,5)、R=1/2、(g0,g1) 顺序、零初终状态、两个零尾位及 Viterbi 平局行为均未改动。两条链路分别执行无交织的“编码→传输坐标突发→译码”和有交织的“编码→交织→同传输坐标突发→反交织→译码”，并核实实际长度、填充、错误索引及信息统计分母。

## 验证结果

所有命令均在 `backend` 目录执行，退出码均为 0：

- `python -m pytest -q test_stage11_interleaving.py`：**38 passed, 0 failed, 0 warnings**。
- `python -m pytest -q test_stage11_interleaving_oracle.py`：**24 passed, 0 failed, 0 warnings**。
- `python -m pytest -q test_stage10_convolutional_coding.py test_stage10_mathematical_oracle.py`：**34 passed, 0 failed, 0 warnings**。
- `python -m pytest -q`：**658 passed, 0 failed, 5 warnings**。
- `git diff --check`：通过，无空白错误。

完整后端的 5 条 warning 是既有测试触发的 NumPy 溢出运行时提示 3 条及 HTTPX 原始内容参数弃用提示 2 条，未来自本轮新模块。

隔离变异负对照均检出：反转读取顺序、错误逆排列、遗漏最后一块、把填充当有效位、把译码 BER 分母错设为编码位数。变异夹具仅在新测试内构造，没有改动生产文件。

## 限制与后续

本轮未实现或验证 FastAPI API、`#/stage11` 前端、浏览器行为、真实远端部署、多帧/软判决/随机统计实验；不声称浏览器验收通过。未发现影响正确性或核心流程的 P0/P1 问题。Phase 3 建议在独立变更中新增有界参数的 Stage11 实验 API：调用本生产核心并返回有效/填充长度、来源映射摘要、突发起点和翻转索引、译码信息误码数/分母及 BER，分别报告信道与译码统计；随后再开发 UI 并做真实浏览器验收。API 不应暴露内部堆栈，也不应把信道翻转计数当成信息误码。
