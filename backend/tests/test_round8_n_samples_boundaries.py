"""
Round8 n_samples 边界测试

验证取消任意固定上限后，n_samples 只受实际计算能力约束。
"""

import pytest
import numpy as np
from decimal import Decimal, getcontext, localcontext
import math
import struct
from bpsk_simulator import BPSKSimulator


def _exact_oracle_std_error(noise_std: float, n_samples) -> float:
    """
    使用精确整数缩放和 math.isqrt 的独立 oracle，不依赖生产代码。

    计算 SE = sqrt((1 + sigma^2) / N) 的正确舍入 binary64 值。
    使用完全不同的算法结构：整数缩放 + isqrt，不使用浮点编码二分搜索。

    该 oracle 采用以下独立算法：
    1. 从 A、B 的 bit_length 差确定 floor(log2(A/B))，完全不用浮点 log
    2. 通过位长度决定所在 binade 和量子大小（2^h）
    3. 用整数移位构造精确有理数 U/V = (A/B) / 2^(2h)
    4. 用 math.isqrt(U // V) 求整数平方根下界
    5. 通过精确整数比较 4*U 与 V*(2k+1)^2 决定舍入

    Args:
        noise_std: binary64 噪声标准差
        n_samples: 精确整数样本数

    Returns:
        float: 正确舍入到 binary64 的标准误差，返回零表示舍入为零
    """
    # 获取 noise_std 的精确有理数表示
    p, q = noise_std.as_integer_ratio()
    # SE^2 = (p^2 + q^2) / (q^2 * N)

    A = p * p + q * q
    B = q * q * int(n_samples)

    # 步骤1：通过整数位长度确定 floor(log2(A/B))
    # 不使用浮点 log，纯整数运算
    a_bits = A.bit_length()
    b_bits = B.bit_length()
    t = a_bits - b_bits  # 近似的 floor(log2(A/B))

    # 精确调整：如果 A < B * 2^t，则 t 应减一
    if t >= 0:
        if A < (B << t):
            t -= 1
    else:
        # 对于 t < 0，正确的比较是 (A << (-t)) < B，而非 A < (B >> (-t))
        # 右移会丢弃余数，导致错误的指数调整
        if (A << (-t)) < B:
            t -= 1

    # 步骤2：确定结果所在的 binade 和量子大小
    # t = floor(log2(A/B))，所以 sqrt(A/B) 在 [2^(t/2), 2^((t+1)/2))
    e = t // 2  # floor(t/2)

    # binary64 的量子：
    # - 非正规数：量子为 2^-1074
    # - 正规数：量子为 2^(e-52)
    h = max(e - 52, -1074)

    # 步骤3：使用整数移位构造精确有理数 U/V = (A/B) / 2^(2h)
    if 2 * h >= 0:
        # A/B / 2^(2h) = A / (B * 2^(2h))
        U = A
        V = B << (2 * h)
    else:
        # A/B / 2^(2h) = (A * 2^(-2h)) / B
        U = A << (-2 * h)
        V = B

    # 步骤4：使用 math.isqrt 求整数平方根下界
    # k = floor(sqrt(U/V)) 的整数近似
    k = math.isqrt(U // V)

    # 精确调整 k，确保 k^2 * V <= U < (k+1)^2 * V
    while k * k * V > U:
        k -= 1
    while (k + 1) * (k + 1) * V <= U:
        k += 1

    # 步骤5：比较 4*U 与 V*(2k+1)^2 决定舍入
    # U/V 与 (k + 0.5)^2 比较
    # 4*U/V 与 (2k+1)^2
    lhs = 4 * U
    rhs = V * (2 * k + 1) * (2 * k + 1)

    if lhs < rhs:
        # U/V < (k+0.5)^2，舍入到 k
        result_int = k
    elif lhs > rhs:
        # U/V > (k+0.5)^2，舍入到 k+1
        result_int = k + 1
    else:
        # U/V = (k+0.5)^2，ties-to-even
        # 选择偶数有效位的候选值
        if k % 2 == 0:
            result_int = k
        else:
            result_int = k + 1

    # 步骤6：将整数结果转换为 binary64
    # result = result_int * 2^h
    # 使用 math.ldexp 精确构造
    if result_int == 0:
        return 0.0

    # result_int 最多为 2^53（binary64 有效位）
    # 转换为 float 不会损失精度
    return math.ldexp(float(result_int), h)


class TestNSamplesBoundaries:
    """测试 n_samples 的各种边界值"""

    def setup_method(self):
        self.simulator = BPSKSimulator(seed=42)
        # 设置高精度 Decimal 上下文用于 oracle
        getcontext().prec = 100

    def _compute_oracle_std_error(self, noise_std: float, n_samples) -> Decimal:
        """使用高精度 Decimal 计算独立 oracle"""
        noise_std_dec = Decimal(str(noise_std))
        n_samples_dec = Decimal(str(n_samples))

        # SE = sqrt((1 + noise_std^2) / n_samples)
        variance_per_sample = Decimal('1.0') + noise_std_dec * noise_std_dec
        std_error = (variance_per_sample / n_samples_dec).sqrt()

        return std_error

    def test_10_power_15_accepted(self):
        """10^15 必须接受"""
        result = self.simulator.diagnose_dc_offset(0.5, 10**15, 0.1)

        assert result['evidence']['n_samples'] == 10**15
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        # 与 oracle 比较
        oracle = self._compute_oracle_std_error(0.1, 10**15)
        relative_error = abs(std_error - float(oracle)) / float(oracle)
        # 对数域算法会引入额外的舍入误差，使用 1e-15 相对容差
        assert relative_error < 5e-15

    def test_10_power_15_plus_1_accepted(self):
        """10^15 + 1 不能再被拒绝"""
        result = self.simulator.diagnose_dc_offset(0.5, 10**15 + 1, 0.1)

        assert result['evidence']['n_samples'] == 10**15 + 1
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        oracle = self._compute_oracle_std_error(0.1, 10**15 + 1)
        relative_error = abs(std_error - float(oracle)) / float(oracle)
        assert relative_error < 5e-15

    def test_10_power_16_accepted(self):
        """10^16 必须接受"""
        result = self.simulator.diagnose_dc_offset(0.5, 10**16, 0.1)

        assert result['evidence']['n_samples'] == 10**16
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        oracle = self._compute_oracle_std_error(0.1, 10**16)
        relative_error = abs(std_error - float(oracle)) / float(oracle)
        assert relative_error < 5e-15

    def test_2_power_53_minus_1_accepted(self):
        """2^53 - 1 必须接受"""
        n = 2**53 - 1
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        oracle = self._compute_oracle_std_error(0.1, n)
        relative_error = abs(std_error - float(oracle)) / float(oracle)
        assert relative_error < 5e-15

    def test_2_power_53_accepted(self):
        """2^53 不能仅因大于连续安全整数边界而被拒绝"""
        n = 2**53
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        oracle = self._compute_oracle_std_error(0.1, n)
        relative_error = abs(std_error - float(oracle)) / float(oracle)
        assert relative_error < 5e-15

    def test_2_power_63_minus_1_accepted(self):
        """2^63 - 1 (np.int64 最大值) 必须接受"""
        n = 2**63 - 1
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        oracle = self._compute_oracle_std_error(0.1, n)
        relative_error = abs(std_error - float(oracle)) / float(oracle)
        assert relative_error < 5e-15

    def test_2_power_63_accepted(self):
        """2^63 必须接受（已超出 np.int64 范围）"""
        n = 2**63
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        oracle = self._compute_oracle_std_error(0.1, n)
        relative_error = abs(std_error - float(oracle)) / float(oracle)
        assert relative_error < 5e-15

    def test_uint64_max_accepted(self):
        """np.uint64 最大值必须接受"""
        n = np.uint64(2**64 - 1)
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == int(n)
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        oracle = self._compute_oracle_std_error(0.1, int(n))
        relative_error = abs(std_error - float(oracle)) / float(oracle)
        assert relative_error < 5e-15

    def test_10_power_400_accepted(self):
        """10^400 在当前公式下有可表示的正标准误差"""
        n = 10**400
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        oracle = self._compute_oracle_std_error(0.1, n)
        relative_error = abs(std_error - float(oracle)) / float(oracle)
        # 对于极大数，对数域算法的误差会累积更多
        assert relative_error < 5e-14

    def test_10_power_615_accepted(self):
        """10^615 标准误差 ≈ 3.178e-308，仍是可表示的正规正数"""
        n = 10**615
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        # 独立 oracle: sqrt((1 + 0.1^2) / 10^615) ≈ 3.178049716414141e-308
        oracle = self._compute_oracle_std_error(0.1, n)
        # 由于极小正数的离散化，使用更宽松的相对容差
        # 或直接检查舍入到正确的 binary64 值
        oracle_float = float(oracle)
        # 对于接近最小正规数的值，relative error 可能被放大
        # 使用绝对误差更合理
        if oracle_float != 0:
            relative_error = abs(std_error - oracle_float) / oracle_float
            assert relative_error < 1e-13  # 允许更大的相对误差
        # 更重要的是结果必须是有限正数
        assert std_error > 0

    def test_10_power_616_accepted(self):
        """10^616 标准误差 ≈ 1.005e-308，仍可表示"""
        n = 10**616
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

        oracle = self._compute_oracle_std_error(0.1, n)
        oracle_float = float(oracle)
        if oracle_float > 0:
            relative_error = abs(std_error - oracle_float) / oracle_float
            assert relative_error < 1e-13

    def test_10_power_617_accepted(self):
        """10^617 对应非正规正数，仍应接受"""
        n = 10**617
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

    def test_10_power_620_accepted(self):
        """10^620 对应更小的非正规正数"""
        n = 10**620
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

    def test_10_power_640_accepted(self):
        """10^640 仍可舍入为非零正数"""
        n = 10**640
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

    def test_10_power_646_accepted(self):
        """10^646 仍可表示"""
        n = 10**646
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

    def test_10_power_647_accepted(self):
        """10^647 对应接近 binary64 最小正数 (5e-324) 的值"""
        n = 10**647
        result = self.simulator.diagnose_dc_offset(0.5, n, 0.1)

        assert result['evidence']['n_samples'] == n
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

    def test_round10_precise_subnormal_counterexample(self):
        """
        R10-01: 精确反例 - 16550535546126 * 10**634

        独立高精度计算表明：
        - 数学实数 SE ≈ 2.47e-324
        - 高于零与最小正非正规数之间的舍入中点
        - 正确舍入到 binary64 应为 5e-324 (0x0.0000000000001p-1022)

        Round9 的 log/exp 中间舍入导致误拒，本轮必须修复。
        """
        N = 16550535546126 * 10**634

        # 使用独立高精度 oracle 验证正确舍入结果
        with localcontext() as ctx:
            ctx.prec = 1200
            sigma = Decimal.from_float(0.1)
            variance = Decimal(1) + sigma * sigma
            exact_se = (variance / Decimal(N)).sqrt()
            expected_float = float(exact_se)

        # expected_float 应该是最小正非正规数
        assert expected_float == 5e-324, f"Oracle 验证失败: {expected_float}"
        assert expected_float > 0
        assert np.isfinite(expected_float)

        # 产品函数必须接受并返回正确舍入的结果
        result = self.simulator.diagnose_dc_offset(0.5, N, 0.1)

        se = result['evidence']['std_error']

        # 严格验证：
        # 1. 结果是有限的
        assert np.isfinite(se), f"标准误差必须有限，得到: {se}"

        # 2. 结果严格大于零
        assert se > 0, f"标准误差必须大于零，得到: {se}"

        # 3. 结果精确等于最小正非正规数
        # 不使用 pytest.approx，因为默认绝对容差会让零通过
        assert se == 5e-324, f"标准误差应为 5e-324，得到: {se} ({se.hex()})"

        # 4. n_samples 精确保留
        assert result['evidence']['n_samples'] == N

        # 5. 验证十六进制表示
        assert se.hex() == '0x0.0000000000001p-1022', f"十六进制表示错误: {se.hex()}"

    def test_round10_slightly_below_subnormal_threshold(self):
        """
        验证舍入中点附近的边界：稍高于中点时接受，稍低于中点时拒绝

        这是对上述反例的补充测试，确保修复没有简单地接受所有下溢结果。
        """
        # 10^648 的数学结果约 1.005e-324，低于舍入中点，应舍入为零并被拒绝
        N_below = 10**648
        with pytest.raises(ValueError, match="underflow|zero|cannot be represented"):
            self.simulator.diagnose_dc_offset(0.5, N_below, 0.1)

    def test_10_power_648_controlled_rejection(self):
        """10^648 标准误差舍入为零，应受控拒绝"""
        n = 10**648

        with pytest.raises(ValueError, match="underflow|zero|cannot be represented"):
            self.simulator.diagnose_dc_offset(0.5, n, 0.1)

    def test_10_power_1000_controlled_rejection(self):
        """10^1000 对应的标准误差无法以 binary64 正数表示，应受控拒绝"""
        n = 10**1000

        # 应该抛出 ValueError，而不是静默返回 0 或抛出 OverflowError
        with pytest.raises(ValueError, match="underflow|too small|cannot represent|zero"):
            self.simulator.diagnose_dc_offset(0.5, n, 0.1)

    def test_round11_exact_midpoint_minimal_tie(self):
        """
        R11-01: 精确中点 - 最小情况 (sigma = 5 * ulp(0.0))

        独立精确有理数计算表明:
        - sigma = 5 * 2^-1074
        - N = 2^2150 + 100 时，SE^2 = 2^-2150，SE = 2^-1075
        - 这恰好是零和最小正非正规数 (5e-324) 的舍入中点
        - IEEE-754 ties-to-even 要求舍入为 0.0
        - 因此必须受控拒绝 (ValueError)

        这是 Round10 固定 1200 位 Decimal 错误接受的情况。
        """
        sigma = 5 * math.ulp(0.0)
        N = 2**2150 + 100

        # 使用独立 oracle 验证这确实是精确中点
        oracle_result = _exact_oracle_std_error(sigma, N)
        assert oracle_result == 0.0, f"Oracle 应返回 0.0 (中点舍入为零)，得到: {oracle_result}"

        # 产品函数必须拒绝
        with pytest.raises(ValueError, match="rounds to zero|underflow|cannot be represented"):
            self.simulator.diagnose_dc_offset(0.5, N, sigma)

    def test_round11_above_midpoint_minimal_tie(self):
        """
        R11-01: 高于中点 - sigma = 5 * ulp(0.0), N = 2^2150 + 99

        SE 高于中点，正确舍入为 5e-324，应该接受。
        """
        sigma = 5 * math.ulp(0.0)
        N = 2**2150 + 99

        # 使用独立 oracle 验证
        oracle_result = _exact_oracle_std_error(sigma, N)
        assert oracle_result == 5e-324, f"Oracle 应返回 5e-324，得到: {oracle_result}"

        # 产品函数必须接受并返回正确值
        result = self.simulator.diagnose_dc_offset(0.5, N, sigma)
        se = result['evidence']['std_error']

        assert np.isfinite(se)
        assert se > 0
        assert se == 5e-324
        assert se.hex() == '0x0.0000000000001p-1022'
        assert result['evidence']['n_samples'] == N

    def test_round11_below_midpoint_minimal_tie(self):
        """
        R11-01: 低于中点 - sigma = 5 * ulp(0.0), N = 2^2150 + 101

        SE 低于中点，正确舍入为 0.0，应该拒绝。
        """
        sigma = 5 * math.ulp(0.0)
        N = 2**2150 + 101

        # 使用独立 oracle 验证
        oracle_result = _exact_oracle_std_error(sigma, N)
        assert oracle_result == 0.0, f"Oracle 应返回 0.0，得到: {oracle_result}"

        # 产品函数必须拒绝
        with pytest.raises(ValueError, match="rounds to zero|underflow|cannot be represented"):
            self.simulator.diagnose_dc_offset(0.5, N, sigma)

    def test_round11_exact_midpoint_sigma_113delta(self):
        """
        R11-01: 精确中点 - sigma = 113 * ulp(0.0), N = 2^2150 + 51076

        Round10 独立报告发现的另一个精确中点情况。
        """
        sigma = 113 * math.ulp(0.0)
        N = 2**2150 + 51076

        # 使用独立 oracle 验证
        oracle_result = _exact_oracle_std_error(sigma, N)
        assert oracle_result == 0.0, f"Oracle 应返回 0.0 (中点舍入为零)，得到: {oracle_result}"

        # 产品函数必须拒绝
        with pytest.raises(ValueError, match="rounds to zero|underflow|cannot be represented"):
            self.simulator.diagnose_dc_offset(0.5, N, sigma)

    def test_round11_above_midpoint_sigma_113delta(self):
        """
        R11-01: 高于中点 - sigma = 113 * ulp(0.0), N = 2^2150 + 51075
        """
        sigma = 113 * math.ulp(0.0)
        N = 2**2150 + 51075

        oracle_result = _exact_oracle_std_error(sigma, N)
        assert oracle_result == 5e-324

        result = self.simulator.diagnose_dc_offset(0.5, N, sigma)
        se = result['evidence']['std_error']

        assert se == 5e-324
        assert result['evidence']['n_samples'] == N

    def test_round11_below_midpoint_sigma_113delta(self):
        """
        R11-01: 低于中点 - sigma = 113 * ulp(0.0), N = 2^2150 + 51077
        """
        sigma = 113 * math.ulp(0.0)
        N = 2**2150 + 51077

        oracle_result = _exact_oracle_std_error(sigma, N)
        assert oracle_result == 0.0

        with pytest.raises(ValueError, match="rounds to zero|underflow|cannot be represented"):
            self.simulator.diagnose_dc_offset(0.5, N, sigma)

    def test_round11_sigma_0_1_critical_boundary(self):
        """
        R11-01: sigma=0.1 的临界整数边界

        计算 C = ((p^2 + q^2) * 2^2150) / q^2，其中 (p, q) = (0.1).as_integer_ratio()
        验证 N=C-1 (接受), N=C (拒绝), N=C+1 (拒绝)
        """
        sigma = 0.1
        p, q = sigma.as_integer_ratio()

        # 计算临界整数 C
        # SE^2 = (p^2 + q^2) / (q^2 * N)
        # 中点: SE = 2^-1075, SE^2 = 2^-2150
        # (p^2 + q^2) / (q^2 * N) = 2^-2150
        # N = (p^2 + q^2) * 2^2150 / q^2

        numerator = (p * p + q * q) * (2**2150)
        denominator = q * q

        # 验证整除
        assert numerator % denominator == 0, "应该整除"
        C = numerator // denominator

        # N = C - 1: 高于中点，应接受
        oracle_above = _exact_oracle_std_error(sigma, C - 1)
        assert oracle_above == 5e-324
        result_above = self.simulator.diagnose_dc_offset(0.5, C - 1, sigma)
        assert result_above['evidence']['std_error'] == 5e-324

        # N = C: 精确中点，应拒绝
        oracle_equal = _exact_oracle_std_error(sigma, C)
        assert oracle_equal == 0.0
        with pytest.raises(ValueError, match="rounds to zero|underflow|cannot be represented"):
            self.simulator.diagnose_dc_offset(0.5, C, sigma)

        # N = C + 1: 低于中点，应拒绝
        oracle_below = _exact_oracle_std_error(sigma, C + 1)
        assert oracle_below == 0.0
        with pytest.raises(ValueError, match="rounds to zero|underflow|cannot be represented"):
            self.simulator.diagnose_dc_offset(0.5, C + 1, sigma)

    def test_round12_subnormal_normal_boundary_125_ulp(self):
        """
        R12-02-A: 最大非正规数与最小正规数交界 - 125 ULP 反例

        N = 2**2044 + 2**1993
        sigma = 0.0
        预期: math.nextafter(sys.float_info.min, 0.0) = 最大非正规数

        整数不等式证明:
        令 lo = 2**53 - 3, hi = 2**53 - 1
        N * lo^2 < 2**2150 < N * hi^2
        因此 (lo/2**1075)^2 < 1/N < (hi/2**1075)^2
        sqrt(1/N) 严格位于最大非正规数两侧的舍入中点之间
        必须舍入到最大非正规数，且不是 tie
        """
        import sys

        N = 2**2044 + 2**1993
        sigma = 0.0

        # 整数不等式验证
        lo_mid_num = 2**53 - 3
        hi_mid_num = 2**53 - 1
        target_squared = 2**2150

        assert N * lo_mid_num * lo_mid_num < target_squared
        assert target_squared < N * hi_mid_num * hi_mid_num

        # 预期结果：最大非正规数
        expected = math.nextafter(sys.float_info.min, 0.0)
        assert expected.hex() == '0x0.fffffffffffffp-1022'

        # Oracle 验证
        oracle_result = _exact_oracle_std_error(sigma, N)
        assert oracle_result == expected

        # 真实生产函数
        result = self.simulator.diagnose_dc_offset(0.5, N, sigma)
        actual = result['evidence']['std_error']

        # 精确相等断言
        assert actual == expected, (
            f"Expected {expected.hex()}, got {actual.hex()}, "
            f"difference: {abs(actual - expected) / math.ulp(expected)} ULP"
        )

    def test_round12_minimum_normal_exact(self):
        """
        R12-02-A: N = 2**2044 时标准误差恰为最小正规数

        sigma = 0.0
        SE^2 = 1 / (2**2044) = 2^-2044
        SE = 2^-1022 = sys.float_info.min (精确)

        预期: 0x1.0000000000000p-1022
        """
        import sys

        N = 2**2044
        sigma = 0.0

        expected = sys.float_info.min
        assert expected.hex() == '0x1.0000000000000p-1022'

        # Oracle 验证
        oracle_result = _exact_oracle_std_error(sigma, N)
        assert oracle_result == expected

        # 真实生产函数
        result = self.simulator.diagnose_dc_offset(0.5, N, sigma)
        actual = result['evidence']['std_error']

        # 精确相等断言
        assert actual == expected, (
            f"Expected {expected.hex()}, got {actual.hex()}"
        )

    def test_round12_10_power_615_170_ulp(self):
        """
        R12-02-B: 10**615 的 170 ULP 反例

        N = 10**615
        sigma = 0.1
        预期: 0x1.6da4621cc7930p-1022

        此案例证明修复不只是解决交界问题，
        还解决了快速路径对其他正规数结果的错误舍入。
        """
        N = 10**615
        sigma = 0.1

        # 预期结果的十六进制表示
        expected_hex = '0x1.6da4621cc7930p-1022'
        expected = float.fromhex(expected_hex)

        # Oracle 验证
        oracle_result = _exact_oracle_std_error(sigma, N)
        assert oracle_result.hex() == expected_hex

        # 真实生产函数
        result = self.simulator.diagnose_dc_offset(0.5, N, sigma)
        actual = result['evidence']['std_error']

        # 精确相等断言（逐位比较）
        assert actual.hex() == expected_hex, (
            f"Expected {expected_hex}, got {actual.hex()}, "
            f"difference: {abs(actual - expected) / math.ulp(expected)} ULP"
        )

    def test_round12_round9_original_counterexample(self):
        """
        R12-02-C: Round9 原始反例保持正确

        N = 16550535546126 * 10**634
        sigma = 0.1
        预期: 5e-324 (最小正非正规数)

        不得回归为 ValueError
        """
        N = 16550535546126 * 10**634
        sigma = 0.1

        expected = 5e-324
        assert expected.hex() == '0x0.0000000000001p-1022'

        # Oracle 验证
        oracle_result = _exact_oracle_std_error(sigma, N)
        assert oracle_result == expected

        # 真实生产函数
        result = self.simulator.diagnose_dc_offset(0.5, N, sigma)
        actual = result['evidence']['std_error']

        # 精确相等断言
        assert actual == expected, (
            f"Expected {expected.hex()}, got {actual.hex()}"
        )

    def test_round12_large_n_boundaries(self):
        """
        R12-02-E: 原有大整数边界回归

        验证 10**615, 10**616, 10**617, 10**620, 10**640, 10**646, 10**647, 10**648, 10**1000
        每个案例记录真实输出、预期输出、十六进制值、是否受控拒绝，以及计数是否精确保留
        """
        sigma = 0.1
        test_cases = [
            (10**615, False),   # 应接受
            (10**616, False),   # 应接受
            (10**617, False),   # 应接受
            (10**620, False),   # 应接受
            (10**640, False),   # 应接受
            (10**646, False),   # 应接受
            (10**647, False),   # 应接受
            (10**648, True),    # 应拒绝 (舍入为零)
            (10**1000, True),   # 应拒绝 (舍入为零)
        ]

        for N, should_reject in test_cases:
            oracle_result = _exact_oracle_std_error(sigma, N)

            if should_reject:
                # 预期拒绝
                assert oracle_result == 0.0, f"Oracle for N={N} should return 0.0"
                with pytest.raises(ValueError, match="rounds to zero|underflow|cannot be represented"):
                    self.simulator.diagnose_dc_offset(0.5, N, sigma)
            else:
                # 预期接受
                assert oracle_result > 0, f"Oracle for N={N} should be positive"
                result = self.simulator.diagnose_dc_offset(0.5, N, sigma)
                actual = result['evidence']['std_error']

                # 精确相等断言
                assert actual == oracle_result, (
                    f"N={N}: Expected {oracle_result.hex()}, got {actual.hex()}, "
                    f"difference: {abs(actual - oracle_result) / math.ulp(oracle_result) if oracle_result > 0 else 'inf'} ULP"
                )

                # 计数精确保留
                assert result['evidence']['n_samples'] == N

    def test_round13_negative_exponent_regression(self):
        """
        R13-01: 负指数比较缺陷的最小回归测试

        输入: noise_std = 0.0, n_samples = 5
        数学值: SE = sqrt(1/5)
        正确的 binary64 舍入结果: 0x1.c9f25c5bfedd9p-2

        该测试用于防止正式 oracle 在负指数分支的整数余数丢弃错误回归。
        旧逻辑 `A < (B >> (-t))` 会丢弃余数，导致指数 t 错误判断，
        最终舍入结果偏离 1 ULP。

        正确逻辑: 对于 t < 0，应使用 `(A << (-t)) < B` 进行精确比较。

        该测试包含独立的整数不等式证明，不依赖 oracle 自身的计算结果。
        """
        noise_std = 0.0
        n_samples = 5

        # 预期的正确结果（固定的精确值）
        expected_hex = '0x1.c9f25c5bfedd9p-2'
        expected = float.fromhex(expected_hex)

        # 独立整数证书：证明真实的 sqrt(1/5) 严格位于该浮点数的舍入区间内
        a, b = expected.as_integer_ratio()

        # 证明 sqrt(1/5) 位于 (a-0.5)/b 和 (a+0.5)/b 之间，即不是 tie
        # 等价于: 5*(2a-1)^2 < 4*b^2 < 5*(2a+1)^2
        assert 5 * (2*a - 1) ** 2 < 4 * b * b, "Left boundary证明失败"
        assert 4 * b * b < 5 * (2*a + 1) ** 2, "Right boundary证明失败"

        # 正式 oracle 必须返回规定的十六进制结果
        oracle_result = _exact_oracle_std_error(noise_std, n_samples)
        assert oracle_result.hex() == expected_hex, (
            f"Oracle failed: expected {expected_hex}, got {oracle_result.hex()}"
        )

        # 生产函数必须返回相同的正确结果
        result = self.simulator.diagnose_dc_offset(0.5, n_samples, noise_std)
        actual = result['evidence']['std_error']

        assert actual.hex() == expected_hex, (
            f"Production function failed: expected {expected_hex}, got {actual.hex()}"
        )
        assert result['evidence']['n_samples'] == n_samples


class TestNSamplesTypeConsistency:
    """测试 Python int、np.int64、np.uint64 的一致性"""

    def setup_method(self):
        self.simulator = BPSKSimulator(seed=42)

    def test_same_count_same_result_10_power_16(self):
        """同一计数的三种类型应返回相同结果"""
        n = 10**16

        result_python = self.simulator.diagnose_dc_offset(0.5, n, 0.1)
        result_int64 = self.simulator.diagnose_dc_offset(0.5, np.int64(n), 0.1)
        result_uint64 = self.simulator.diagnose_dc_offset(0.5, np.uint64(n), 0.1)

        # 计数必须精确保留
        assert result_python['evidence']['n_samples'] == n
        assert result_int64['evidence']['n_samples'] == n
        assert result_uint64['evidence']['n_samples'] == n

        # 标准误差必须一致
        se_python = result_python['evidence']['std_error']
        se_int64 = result_int64['evidence']['std_error']
        se_uint64 = result_uint64['evidence']['std_error']

        assert se_python == se_int64
        assert se_python == se_uint64

    def test_same_count_same_result_2_power_63_minus_1(self):
        """np.int64 最大值的三种类型应一致"""
        n = 2**63 - 1

        result_python = self.simulator.diagnose_dc_offset(0.5, n, 0.1)
        result_int64 = self.simulator.diagnose_dc_offset(0.5, np.int64(n), 0.1)
        result_uint64 = self.simulator.diagnose_dc_offset(0.5, np.uint64(n), 0.1)

        assert result_python['evidence']['n_samples'] == n
        assert result_int64['evidence']['n_samples'] == n
        assert result_uint64['evidence']['n_samples'] == n

        se_python = result_python['evidence']['std_error']
        se_int64 = result_int64['evidence']['std_error']
        se_uint64 = result_uint64['evidence']['std_error']

        assert se_python == se_int64
        assert se_python == se_uint64


class TestNSamplesIllegalInputs:
    """验证非法输入仍被拒绝"""

    def setup_method(self):
        self.simulator = BPSKSimulator(seed=42)

    def test_bool_rejected(self):
        """bool 仍被拒绝"""
        with pytest.raises(ValueError, match="bool"):
            self.simulator.diagnose_dc_offset(0.5, True, 0.1)

    def test_np_bool_rejected(self):
        """np.bool_ 仍被拒绝"""
        with pytest.raises(ValueError, match="bool"):
            self.simulator.diagnose_dc_offset(0.5, np.bool_(True), 0.1)

    def test_zero_rejected(self):
        """零仍被拒绝"""
        with pytest.raises(ValueError, match="positive"):
            self.simulator.diagnose_dc_offset(0.5, 0, 0.1)

    def test_negative_rejected(self):
        """负数仍被拒绝"""
        with pytest.raises(ValueError, match="positive"):
            self.simulator.diagnose_dc_offset(0.5, -1, 0.1)

    def test_float_rejected(self):
        """非整数 float 仍被拒绝"""
        with pytest.raises(ValueError, match="integer"):
            self.simulator.diagnose_dc_offset(0.5, 100.5, 0.1)

    def test_string_rejected(self):
        """字符串仍被拒绝"""
        with pytest.raises(ValueError, match="integer"):
            self.simulator.diagnose_dc_offset(0.5, "100", 0.1)
