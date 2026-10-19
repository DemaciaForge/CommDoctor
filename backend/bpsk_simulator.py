"""
BPSK通信系统仿真模块

实现BPSK调制、AWGN信道、硬判决解调和误码率计算
"""

import numpy as np
from scipy.special import erfc
from decimal import Decimal, localcontext
import sys
import math
import struct


def _exact_sqrt_rounded(numerator_squared, denominator_squared):
    """
    计算 sqrt(numerator_squared / denominator_squared) 的正确舍入 binary64 值。

    使用精确整数/有理数比较，不依赖固定精度 Decimal。
    当正确舍入结果为零时返回 0.0；否则返回正确舍入的正有限 binary64。

    Args:
        numerator_squared: 正整数，分子的平方
        denominator_squared: 正整数，分母的平方

    Returns:
        float: 正确舍入到 binary64 的平方根值，可能为 0.0

    算法:
        1. 目标是找到 f = sqrt(A/B) 的正确舍入 binary64，其中 A=numerator_squared, B=denominator_squared
        2. 等价于找到满足 f^2 <= A/B 的最大 binary64 值 f_lo，以及下一个值 f_hi
        3. 对 binary64 的位编码进行二分搜索（利用非负有限 binary64 的位编码单调性）
        4. 使用精确整数交叉乘法比较 f^2 与 A/B，避免浮点舍入
        5. 通过比较 A/B 与 (f_lo + f_hi)/2 的平方，决定舍入方向
        6. 中点相等时，按 ties-to-even 规则选择有效位最低位为偶数的候选
    """
    A = int(numerator_squared)
    B = int(denominator_squared)

    if A <= 0 or B <= 0:
        raise ValueError("Both arguments must be positive integers")

    # 使用二分搜索找到满足 candidate^2 <= A/B 的最大 binary64
    # 搜索区间：[0.0, +inf) 映射到 binary64 位编码 [0x0000000000000000, 0x7FF0000000000000)
    # 0x0000000000000000: +0.0
    # 0x0000000000000001: 最小正非正规数 (5e-324)
    # 0x000FFFFFFFFFFFFF: 最大非正规数 (约 2.225e-308)
    # 0x0010000000000000: 最小正规数 (sys.float_info.min)
    # 0x7FEFFFFFFFFFFFFF: 最大有限数 (sys.float_info.max)
    # 0x7FF0000000000000: +inf

    left_bits = 0x0000000000000000
    right_bits = 0x7FF0000000000000  # +inf，但实际上不会达到

    # 为了避免处理 inf，先快速检查上界
    # 如果 A/B > max_float^2，那么结果会溢出（但我们的应用场景不会发生）
    # 这里先假设结果在有限范围内

    # 二分搜索找到 f_lo
    while right_bits - left_bits > 1:
        mid_bits = (left_bits + right_bits) // 2
        mid_float = struct.unpack('>d', struct.pack('>Q', mid_bits))[0]

        # 比较 mid_float^2 与 A/B
        # mid_float^2 <= A/B  ⟺  mid_float^2 * B <= A
        mid_p, mid_q = mid_float.as_integer_ratio()
        # mid_float = mid_p / mid_q, mid_float^2 = mid_p^2 / mid_q^2
        # mid_p^2 / mid_q^2 <= A / B  ⟺  mid_p^2 * B <= A * mid_q^2

        if mid_p * mid_p * B <= A * mid_q * mid_q:
            left_bits = mid_bits
        else:
            right_bits = mid_bits

    # 现在 left_bits 是满足 f^2 <= A/B 的最大位编码
    f_lo = struct.unpack('>d', struct.pack('>Q', left_bits))[0]

    # f_hi 是下一个可表示的 binary64 值
    if left_bits + 1 >= 0x7FF0000000000000:
        # 已经是最大有限数或接近 +inf
        # 在我们的应用中不应该到达这里（标准误差不会那么大）
        return f_lo

    f_hi = struct.unpack('>d', struct.pack('>Q', left_bits + 1))[0]

    # 现在需要决定舍入到 f_lo 还是 f_hi
    # 计算 (f_lo + f_hi) / 2 的精确有理数表示
    # f_lo = p_lo / q_lo, f_hi = p_hi / q_hi
    p_lo, q_lo = f_lo.as_integer_ratio()
    p_hi, q_hi = f_hi.as_integer_ratio()

    # midpoint = (f_lo + f_hi) / 2 = (p_lo/q_lo + p_hi/q_hi) / 2
    #          = (p_lo*q_hi + p_hi*q_lo) / (2*q_lo*q_hi)
    midpoint_num = p_lo * q_hi + p_hi * q_lo
    midpoint_den = 2 * q_lo * q_hi

    # midpoint^2 = midpoint_num^2 / midpoint_den^2
    # 比较 A/B 与 midpoint^2
    # A/B < midpoint^2  ⟺  A * midpoint_den^2 < B * midpoint_num^2  →  舍入到 f_lo
    # A/B > midpoint^2  ⟺  A * midpoint_den^2 > B * midpoint_num^2  →  舍入到 f_hi
    # A/B = midpoint^2  →  ties-to-even

    lhs = A * midpoint_den * midpoint_den
    rhs = B * midpoint_num * midpoint_num

    if lhs < rhs:
        # A/B 小于中点，舍入到 f_lo
        return f_lo
    elif lhs > rhs:
        # A/B 大于中点，舍入到 f_hi
        return f_hi
    else:
        # 精确位于中点，ties-to-even
        # 需要选择有效位最低位为偶数的候选
        # 对于 binary64，检查位编码的最低位
        lo_bits = left_bits
        hi_bits = left_bits + 1

        # 偶数位编码对应 ties-to-even 的"偶数"
        if lo_bits % 2 == 0:
            return f_lo
        else:
            return f_hi


class BPSKSimulator:
    """BPSK通信系统仿真器"""

    def __init__(self, seed: int = None):
        """
        初始化仿真器

        Args:
            seed: 随机种子，用于结果可复现
        """
        self.rng = np.random.default_rng(seed)
        self.seed = seed

    @staticmethod
    def _safe_scalar_to_float(value, param_name="parameter"):
        """
        安全地将数值标量转换为 Python float

        防止：
        1. NumPy 整数在算术运算中回绕（uint8, int8 等）
        2. Python 超大整数无法转换
        3. object dtype 泄漏 TypeError
        4. complex 值被静默处理

        Args:
            value: 输入值（标量）
            param_name: 参数名称，用于错误消息

        Returns:
            Python float

        Raises:
            ValueError: 输入不是有效的实数标量
        """
        # 拒绝 complex
        if isinstance(value, complex) or (hasattr(value, 'dtype') and np.issubdtype(type(value), np.complexfloating)):
            raise ValueError(f"{param_name} must be real-valued (got complex)")

        # Round6修复：拒绝字符串类型（即使可以被 float() 转换）
        if isinstance(value, str):
            raise ValueError(f"{param_name} must be numeric, not string")

        # Round7修复：拒绝 bytes 类型（Python bytes 和 NumPy bytes_）
        if isinstance(value, (bytes, np.bytes_)):
            raise ValueError(f"{param_name} must be numeric, not bytes")

        # 拒绝数组（包括零维数组）
        if isinstance(value, np.ndarray):
            # Round6修复：在解包零维数组前检查 object dtype
            if value.dtype == object:
                raise ValueError(f"{param_name} with object dtype is not supported")

            # Round7修复：在解包零维数组前检查 bytes dtype
            if value.dtype.kind in ('S', 'a'):  # 'S': bytes_, 'a': 旧版 bytes
                raise ValueError(f"{param_name} must be numeric, not bytes array")

            if value.ndim == 0:
                # 零维数组：提取标量后递归
                return BPSKSimulator._safe_scalar_to_float(value.item(), param_name)
            else:
                raise ValueError(f"{param_name} must be a scalar, not an array")

        # 拒绝 object（在转换前检查）
        if hasattr(value, 'dtype') and value.dtype == object:
            raise ValueError(f"{param_name} with object dtype is not supported")

        # 尝试转换为 Python float
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError) as e:
            # TypeError: 不支持的类型（如 object 数组元素）
            # ValueError: 无法转换
            # OverflowError: Python 大整数超出 float 范围
            raise ValueError(f"{param_name} cannot be converted to a valid float: {e}") from e

        # 验证结果是有限的（不检查范围，让后续代码决定）
        if not np.isfinite(result):
            raise ValueError(f"{param_name} must be finite (got {result})")

        return result


    def generate_bits(self, n_bits: int) -> np.ndarray:
        """
        生成随机比特序列

        Args:
            n_bits: 比特数量

        Returns:
            长度为n_bits的0/1比特数组
        """
        return self.rng.integers(0, 2, size=n_bits, dtype=np.int32)

    def modulate_bpsk(self, bits: np.ndarray) -> np.ndarray:
        """
        BPSK调制：0 -> -1, 1 -> +1

        Args:
            bits: 输入比特序列(0/1)，支持整数或布尔数组

        Returns:
            BPSK符号序列(±1)

        Raises:
            ValueError: 输入包含非0/1值或不支持的类型
        """
        # F04修复：实施严格dtype白名单策略
        # 步骤1：转换为数组（不进行强制类型转换）
        bits_array = np.asarray(bits)

        # P2-A修复：拒绝空数组（必须在任何其他检查之前，包括多维空数组）
        # 检查 size==0 而不是 len，因为 size 对多维数组也有效
        if bits_array.size == 0:
            raise ValueError("bits cannot be empty")

        # P2-A扩展修复：确保是一维数组（在 dtype 检查之前）
        if bits_array.ndim != 1:
            raise ValueError(f"bits must be 1-dimensional, got shape {bits_array.shape}")

        # 步骤2：检查dtype.kind是否在白名单内（i=有符号整数, u=无符号整数, b=布尔）
        if bits_array.dtype.kind not in ('i', 'u', 'b'):
            # 提供明确的错误信息
            dtype_name = str(bits_array.dtype)
            if np.issubdtype(bits_array.dtype, np.complexfloating):
                raise ValueError("Complex numbers are not supported. Bits must be 0 or 1 (integer or boolean).")
            elif bits_array.dtype == object:
                raise ValueError("Object dtype arrays are not supported. Bits must be 0 or 1 (integer or boolean).")
            elif np.issubdtype(bits_array.dtype, np.str_) or np.issubdtype(bits_array.dtype, np.bytes_):
                raise ValueError("String inputs are not supported. Bits must be 0 or 1 (integer or boolean).")
            elif np.issubdtype(bits_array.dtype, np.floating):
                raise ValueError("Float inputs not allowed (including 0.0, 1.0). Bits must be integer or boolean.")
            elif np.issubdtype(bits_array.dtype, np.datetime64):
                raise ValueError(f"Datetime dtype '{dtype_name}' is not supported. Bits must be 0 or 1 (integer or boolean).")
            elif np.issubdtype(bits_array.dtype, np.timedelta64):
                raise ValueError(f"Timedelta dtype '{dtype_name}' is not supported. Bits must be 0 or 1 (integer or boolean).")
            elif bits_array.dtype.names is not None:
                # 结构化数组（包含字段名）
                raise ValueError(f"Structured dtype with fields {bits_array.dtype.names} is not supported. Bits must be 0 or 1 (integer or boolean).")
            else:
                raise ValueError(f"Unsupported dtype '{dtype_name}'. Bits must be integer (int8-64, uint8-64) or boolean.")

        # 步骤3：对整数类型，在任何转换之前检查所有元素必须为0或1
        if bits_array.dtype.kind in ('i', 'u'):
            if not np.all((bits_array == 0) | (bits_array == 1)):
                invalid_mask = (bits_array != 0) & (bits_array != 1)
                if np.any(invalid_mask):
                    invalid_values = bits_array[invalid_mask]
                    # 显示前几个非法值
                    sample = invalid_values[:5].tolist() if len(invalid_values) > 5 else invalid_values.tolist()
                    raise ValueError(f"Input bits must contain only 0 or 1, found invalid values: {sample}")

        # 步骤4：安全转换为int32
        bits_int = bits_array.astype(np.int32)

        # 步骤5：最终验证（布尔类型的检查）
        if not np.all((bits_int == 0) | (bits_int == 1)):
            raise ValueError("Input bits must contain only 0 or 1")

        # 步骤6：映射到-1和+1
        return 2 * bits_int - 1

    def add_awgn(self, symbols: np.ndarray, eb_n0_db: float) -> np.ndarray:
        """
        添加加性高斯白噪声

        Args:
            symbols: 发送符号序列
            eb_n0_db: Eb/N0 (dB)

        Returns:
            接收信号 = 发送符号 + 噪声

        Raises:
            ValueError: 符号序列包含非有限值、为复数、为空，或Eb/N0为非有限值或溢出
        """
        # P2-5修复：验证输入不是复数（必须在有限性检查之前）
        symbols_array = np.asarray(symbols)

        # P2-B修复：拒绝 Python 超大整数（在 isfinite 之前）
        if symbols_array.dtype == object:
            raise ValueError("symbols must be numeric array (object dtype not supported)")

        if np.iscomplexobj(symbols_array):
            raise ValueError("symbols must be real-valued (complex dtype not supported)")

        # Round6修复：拒绝非实数dtype（字符串等）
        if symbols_array.dtype.kind not in ('i', 'u', 'f', 'b'):
            raise ValueError(f"symbols must have numeric dtype (got dtype={symbols_array.dtype})")

        # P2-F01修复：拒绝空数组
        if symbols_array.size == 0:
            raise ValueError("symbols cannot be empty")

        # AUD4-01修复：验证输入信号有限性
        if not np.all(np.isfinite(symbols_array)):
            raise ValueError("symbols must contain only finite values (not NaN or Infinity)")

        # P2-F03修复：验证Eb/N0不是复数（必须在finite检查之前）
        if isinstance(eb_n0_db, (np.complexfloating, complex)):
            raise ValueError("eb_n0_db must be real-valued (complex numbers not supported)")

        # P2-03修复：在任何运算前安全转换 eb_n0_db 为 Python float
        # 防止 NumPy 整数回绕（np.uint8(10) 的 -10 变成 246）
        eb_n0_db = self._safe_scalar_to_float(eb_n0_db, "eb_n0_db")

        # AUD4-03修复：使用数学稳定的公式计算噪声标准差
        # 原公式: noise_std = sqrt(1 / (2 * 10^(Eb/N0_dB/10)))
        # 稳定公式: noise_std = sqrt(1/2) * 10^(-Eb/N0_dB/20)
        # 这样避免先计算巨大的正指数再求倒数
        try:
            # sqrt(1/2) ≈ 0.7071067811865476
            noise_std = np.sqrt(0.5) * (10.0 ** (-eb_n0_db / 20.0))

            # 验证结果有限且为正
            if not np.isfinite(noise_std):
                raise ValueError(f"Computed noise_std is not finite for eb_n0_db={eb_n0_db}")
            if noise_std <= 0:
                raise ValueError(f"Computed noise_std is not positive for eb_n0_db={eb_n0_db}")

        except (OverflowError, FloatingPointError) as e:
            raise ValueError(f"eb_n0_db={eb_n0_db} exceeds computational range") from e

        noise = self.rng.normal(0, noise_std, size=symbols_array.shape)
        result = symbols_array + noise

        # P2-5修复：验证输出有限性（防止极值输入相加溢出）
        if not np.all(np.isfinite(result)):
            raise ValueError("Addition of symbols and noise resulted in overflow (non-finite values)")

        return result

    def demodulate_bpsk(self, received: np.ndarray) -> np.ndarray:
        """
        BPSK硬判决解调：>0 -> 1, <=0 -> 0

        Args:
            received: 接收信号

        Returns:
            解调比特序列(0/1)

        Raises:
            ValueError: 接收信号包含非有限值或为复数或为空
        """
        # P2-02修复：拒绝 object dtype（必须在 isfinite 之前，因为 isfinite 不支持 object）
        received_array = np.asarray(received)
        if received_array.dtype == object:
            raise ValueError("received signal must not have object dtype")

        # P2-5修复：验证输入不是复数（必须在有限性检查之前）
        if np.iscomplexobj(received_array):
            raise ValueError("received signal must be real-valued (complex dtype not supported)")

        # Round6修复：拒绝非实数dtype（字符串等）
        if received_array.dtype.kind not in ('i', 'u', 'f', 'b'):
            raise ValueError(f"received signal must have numeric dtype (got dtype={received_array.dtype})")

        # P2-F01修复：拒绝空数组
        if received_array.size == 0:
            raise ValueError("received signal cannot be empty")

        # AUD4-01修复：验证接收信号有限性
        if not np.all(np.isfinite(received_array)):
            raise ValueError("received signal must contain only finite values (not NaN or Infinity)")

        return (received_array > 0).astype(np.int32)

    def calculate_ber_theoretical(self, eb_n0_db: float) -> float:
        """
        计算理论误码率

        公式: Pb = 0.5 * erfc(sqrt(10^(Eb/N0_dB/10)))

        Args:
            eb_n0_db: Eb/N0 (dB)

        Returns:
            理论BER

        Raises:
            ValueError: Eb/N0为非有限值、复数或溢出
        """
        # P2-03修复：安全转换为 Python float（防止大整数/complex/object TypeError）
        eb_n0_db = self._safe_scalar_to_float(eb_n0_db, "eb_n0_db")

        # P2-F02修复：使用稳定公式避免正指数溢出
        # 原公式: 10^(Eb/N0/10) 在大Eb/N0时会溢出
        # 等价变换: sqrt(10^(Eb/N0/10)) = 10^(Eb/N0/20)
        try:
            exponent = eb_n0_db / 20.0
            sqrt_eb_n0_linear = 10.0 ** exponent

            # 验证结果有限
            if not np.isfinite(sqrt_eb_n0_linear):
                raise ValueError(f"eb_n0_db={eb_n0_db} results in non-representable value")

            return 0.5 * erfc(sqrt_eb_n0_linear)
        except (OverflowError, FloatingPointError) as e:
            raise ValueError(f"eb_n0_db={eb_n0_db} exceeds computational range") from e

    def calculate_ber_measured(self, tx_bits: np.ndarray,
                               rx_bits: np.ndarray) -> tuple[float, int]:
        """
        计算实测误码率

        Args:
            tx_bits: 发送比特
            rx_bits: 接收比特

        Returns:
            (实测BER, 错误比特数)

        Raises:
            ValueError: 输入为空、非有限、形状不匹配或包含非法值
        """
        # AUD3-02修复：拒绝空数组
        tx_array = np.asarray(tx_bits)
        rx_array = np.asarray(rx_bits)

        if tx_array.size == 0:
            raise ValueError("tx_bits cannot be empty")
        if rx_array.size == 0:
            raise ValueError("rx_bits cannot be empty")

        # AUD3-06修复：验证shape一致性，防止广播
        if tx_array.ndim != 1:
            raise ValueError(f"tx_bits must be 1-dimensional, got shape {tx_array.shape}")
        if rx_array.ndim != 1:
            raise ValueError(f"rx_bits must be 1-dimensional, got shape {rx_array.shape}")

        if len(tx_array) != len(rx_array):
            raise ValueError(f"tx_bits and rx_bits must have same length, got {len(tx_array)} vs {len(rx_array)}")

        # AUD4-02修复：拒绝complex dtype（在检查0/1之前）
        if np.iscomplexobj(tx_array):
            raise ValueError("tx_bits must be real-valued (complex dtype not supported)")
        if np.iscomplexobj(rx_array):
            raise ValueError("rx_bits must be real-valued (complex dtype not supported)")

        # P2-C修复：拒绝 object dtype（object 数组可能包含 complex 或其他非标准类型）
        # 为了与 modulate_bpsk 的严格 dtype 白名单保持一致，BER 计算也应拒绝 object
        if tx_array.dtype == object:
            raise ValueError("tx_bits must be integer or boolean array (object dtype not supported)")
        if rx_array.dtype == object:
            raise ValueError("rx_bits must be integer or boolean array (object dtype not supported)")

        # P2-C修复：拒绝 float dtype（与 modulate_bpsk 保持一致）
        if tx_array.dtype.kind == 'f':
            raise ValueError("tx_bits must be integer or boolean array (float dtype not supported)")
        if rx_array.dtype.kind == 'f':
            raise ValueError("rx_bits must be integer or boolean array (float dtype not supported)")

        # AUD3-01修复：验证发送比特合法性（0/1整数）
        if not np.all((tx_array == 0) | (tx_array == 1)):
            raise ValueError("tx_bits must contain only 0 or 1")

        # 验证接收比特合法性
        if not np.all((rx_array == 0) | (rx_array == 1)):
            raise ValueError("rx_bits must contain only 0 or 1")

        # 计算错误
        errors = np.sum(tx_array != rx_array)
        ber = errors / len(tx_array)

        # AUD3-06修复：验证BER在[0,1]范围内（防止广播错误）
        if not (0 <= ber <= 1):
            raise ValueError(f"Computed BER {ber} is outside valid range [0,1], possible input shape mismatch")

        return ber, int(errors)

    def demodulate_bpsk_with_threshold(self, received: np.ndarray,
                                       threshold: float = 0.0) -> np.ndarray:
        """
        BPSK硬判决解调，使用可调节门限

        Args:
            received: 接收信号
            threshold: 判决门限，默认为0

        Returns:
            解调比特序列(0/1)

        Raises:
            ValueError: 门限或接收信号包含非有限值、为空或为复数
        """
        # P2修复 + B07修复：安全转换并验证门限（处理超大整数、object等）
        threshold = self._safe_scalar_to_float(threshold, "threshold")

        # P2-2修复：拒绝空数组
        rx_array = np.asarray(received)
        if rx_array.size == 0:
            raise ValueError("received signals cannot be empty")

        # P2-5修复：拒绝复数输入，包括object数组
        if np.iscomplexobj(rx_array) or rx_array.dtype == object:
            raise ValueError("received signals must be real-valued (complex numbers not supported)")

        # Round6修复：拒绝非实数dtype（字符串、object等）
        if rx_array.dtype.kind not in ('i', 'u', 'f', 'b'):
            raise ValueError(f"received signals must have numeric dtype (got dtype={rx_array.dtype})")

        # P2修复：拒绝包含非有限值的接收信号
        if not np.all(np.isfinite(rx_array)):
            raise ValueError("received signals must contain only finite values (not NaN or Infinity)")

        return (rx_array > threshold).astype(np.int32)

    def add_dc_offset(self, signals: np.ndarray, dc_offset: float) -> np.ndarray:
        """
        添加DC偏移故障

        Args:
            signals: 输入信号
            dc_offset: DC偏移值

        Returns:
            添加DC偏移后的信号

        Raises:
            ValueError: dc_offset包含非有限值，或输入信号为复数/非有限
        """
        # P2-03修复：安全转换 dc_offset（防止大整数/complex/object TypeError）
        dc_offset = self._safe_scalar_to_float(dc_offset, "dc_offset")

        # P2-02修复：拒绝 object dtype 信号
        sig_array = np.asarray(signals)
        if np.iscomplexobj(sig_array) or sig_array.dtype == object:
            raise ValueError("signals must be real-valued (complex numbers not supported)")

        # Round6修复：拒绝非实数dtype（字符串等）
        if sig_array.dtype.kind not in ('i', 'u', 'f', 'b'):
            raise ValueError(f"signals must have numeric dtype (got dtype={sig_array.dtype})")

        # P2-F01修复：拒绝空数组
        if sig_array.size == 0:
            raise ValueError("signals cannot be empty")

        # AUD3-01修复：拒绝非有限信号
        if not np.all(np.isfinite(sig_array)):
            raise ValueError("signals must contain only finite values (not NaN or Infinity)")

        # P2-F04修复：将整数信号转换为float以防止加法回绕
        if np.issubdtype(sig_array.dtype, np.integer):
            sig_array = sig_array.astype(np.float64)

        # 执行加法
        result = sig_array + dc_offset

        # P2-4修复：检查加法结果溢出
        if result.size > 0 and not np.all(np.isfinite(result)):
            raise ValueError("DC offset addition resulted in overflow (non-finite values)")

        return result

    def calculate_rx_mean(self, rx_signals: np.ndarray) -> float:
        """
        计算接收信号均值（用于DC偏移估计）

        Args:
            rx_signals: 接收信号数组

        Returns:
            信号均值

        Raises:
            ValueError: 接收信号为空、包含非有限值或为复数类型
        """
        # P2-2修复：拒绝空数组
        rx_array = np.asarray(rx_signals)
        if rx_array.size == 0:
            raise ValueError("rx_signals cannot be empty")

        # P2-5修复：拒绝复数输入，包括object数组
        if np.iscomplexobj(rx_array) or rx_array.dtype == object:
            raise ValueError("rx_signals must be real-valued (complex numbers not supported)")

        # Round7修复：拒绝非数值 dtype（字符串、bytes 等）
        if rx_array.dtype.kind not in ('f', 'i', 'u', 'b'):
            raise ValueError(f"rx_signals must have numeric dtype (got dtype={rx_array.dtype})")

        # P2修复：拒绝包含非有限值的接收信号
        if not np.all(np.isfinite(rx_array)):
            raise ValueError("rx_signals must contain only finite values (not NaN or Infinity)")

        # P2-4修复：计算均值后检查结果有限性
        mean_val = np.mean(rx_array)
        if not np.isfinite(mean_val):
            raise ValueError("Calculated mean is not finite (possible overflow from extreme values)")

        return float(mean_val)

    def diagnose_dc_offset(self, rx_mean: float, n_samples: int,
                          noise_std: float) -> dict:
        """
        基于接收信号均值诊断DC偏移

        Args:
            rx_mean: 接收信号均值
            n_samples: 样本数量
            noise_std: 噪声标准差

        Returns:
            诊断结果字典

        Raises:
            ValueError: 任何参数包含非有限值，或样本数不合法
        """
        # P2-03修复：安全转换所有标量参数
        rx_mean = self._safe_scalar_to_float(rx_mean, "rx_mean")
        noise_std = self._safe_scalar_to_float(noise_std, "noise_std")

        # 验证 noise_std 非负
        if noise_std < 0:
            raise ValueError("noise_std must be non-negative")

        # P2-04修复：sample_size 验证
        # AUD3-03修复：明确拒绝Python bool类型和 np.bool_
        if isinstance(n_samples, (bool, np.bool_)):
            raise ValueError("n_samples must be a true integer, not bool")

        # P2-3修复：验证样本数量
        if not isinstance(n_samples, (int, np.integer)):
            raise ValueError("n_samples must be an integer")
        if n_samples <= 0:
            raise ValueError("n_samples must be positive")

        # Round8修复：取消任意固定 n_samples 上限，改用实际计算安全性判断
        # 方案B：只要能安全完成标准误差计算并产生有效、可表示的结果，就接受
        #
        # 计数契约：
        # 1. Python int、np.int64、np.uint64 对同一合法计数遵循一致契约
        # 2. 返回的 n_samples 必须保留原始整数值（不因 float 转换改变）
        # 3. 标准误差公式：SE = sqrt((1 + noise_std^2) / n_samples)
        # 4. 对可安全计算的计数返回有限正标准误差
        # 5. 对无法表示的标准误差受控拒绝（ValueError），不返回 0/Inf/NaN
        # 6. 不产生未处理异常（OverflowError、TypeError 等）
        #
        # 数值分析：
        # - 使用对数域算法计算标准误差，避免直接转换任意大整数到 float
        # - log(SE) = 0.5 * (log(1 + noise_std^2) - log(n_samples))
        # - 检查结果是否可表示为有限正 binary64 值
        # - 保留原整数计数（不使用浮点近似）

        # D组修复：修正标准误差公式
        # 对于独立BPSK符号 s ~ ±1（等概率）和AWGN n ~ N(0, sigma²)
        # 接收信号 r = s + n + d
        # 其中 Var(s) = 1, Var(n) = sigma²
        # 因此 SE(mean(r)) = sqrt((1 + sigma²) / N)

        # AUD4-03修复：使用安全的平方计算，捕获溢出
        try:
            noise_variance = noise_std * noise_std  # 使用乘法而非幂运算
            if not np.isfinite(noise_variance):
                raise ValueError("noise_std squared resulted in overflow")

            variance_per_sample = 1.0 + noise_variance  # Var(s) + Var(n)

        except (OverflowError, FloatingPointError) as e:
            raise ValueError(f"Variance calculation overflowed for noise_std={noise_std}") from e

        # AUD3-04修复：检查平方和方差计算的有限性
        if not np.isfinite(variance_per_sample):
            raise ValueError("Variance calculation resulted in overflow (non-finite value)")

        # R12-01修复：直接使用精确有理数算法计算标准误差
        # 不再依赖 log/exp 快速路径，消除正规数/非正规数边界的舍入误差
        #
        # SE = sqrt((1 + sigma^2) / N)
        # 其中 sigma = noise_std (binary64), N = n_samples (精确整数)
        #
        # 使用精确整数/有理数比较进行正确舍入：
        # 1. 获取 noise_std 的精确有理数表示
        # 2. 构造 SE^2 = (q^2 + p^2) / (q^2 * N)
        # 3. 使用 _exact_sqrt_rounded 计算正确舍入的 binary64 值
        # 4. 若舍入为零则受控拒绝
        # 5. 完整输入域均使用精确舍入，无快速路径遗漏

        try:
            # 获取 noise_std 的精确有理数表示
            p, q = noise_std.as_integer_ratio()
            # noise_std = p/q, noise_std^2 = p^2/q^2
            # 1 + noise_std^2 = 1 + p^2/q^2 = (q^2 + p^2) / q^2

            # SE^2 = (q^2 + p^2) / (q^2 * N)
            # SE = sqrt((q^2 + p^2) / (q^2 * N))

            numerator_squared = p * p + q * q
            denominator_squared = q * q * int(n_samples)

            # 使用精确舍入函数计算正确舍入的 SE
            # 此路径适用于所有输入，从最小非正规到最大，无例外
            std_error = _exact_sqrt_rounded(numerator_squared, denominator_squared)

            # 如果精确舍入结果为零，则受控拒绝
            if std_error == 0.0:
                raise ValueError(
                    f"Standard error correctly rounds to zero for n_samples={n_samples}. "
                    f"Result cannot be represented as a positive binary64 number."
                )
            # 否则接受精确舍入的结果（可能是最小正非正规数或更大值）

        except (ValueError) as e:
            # 捕获精确计算中的异常
            raise ValueError(
                f"Failed to compute standard error for n_samples={n_samples}: {e}"
            ) from e

        # 检查 SE 的有限性和正数性
        # 这里检查实际 binary64 结果，而不是预设门槛
        if not math.isfinite(std_error):
            raise ValueError(
                f"Standard error calculation resulted in non-finite value "
                f"for n_samples={n_samples}"
            )

        if std_error <= 0:
            # 这个检查现在只作为额外的安全网
            # 正常情况下，高精度回退已经处理了零值情况
            raise ValueError(
                f"Standard error underflow to zero for n_samples={n_samples}. "
                f"Result cannot be represented as a positive binary64 number."
            )

        # 使用3-sigma准则判断是否存在显著偏移
        threshold = 3 * std_error

        # 检查门限有限性
        if not np.isfinite(threshold):
            raise ValueError("Threshold calculation resulted in overflow (non-finite value)")

        has_offset = abs(rx_mean) > threshold
        confidence = "高" if abs(rx_mean) > 5 * std_error else "中" if has_offset else "低"

        diagnosis = {
            'has_dc_offset': bool(has_offset),  # A组修复：转换numpy.bool_为Python bool
            'estimated_offset': float(rx_mean),
            'confidence': confidence,
            'evidence': {
                'rx_mean': float(rx_mean),
                'std_error': float(std_error),
                'threshold_3sigma': float(threshold),
                'n_samples': int(n_samples)  # 确保整数也是Python类型
            }
        }

        # 生成中文诊断信息
        if has_offset:
            direction = "正向" if rx_mean > 0 else "负向"
            diagnosis['message'] = (
                f"检测到{direction}DC偏移。接收信号均值为{rx_mean:.4f}，"
                f"超过3σ阈值({threshold:.4f})。建议调整判决门限补偿此偏移。"
            )
            diagnosis['suggested_threshold'] = float(rx_mean)
        else:
            diagnosis['message'] = (
                f"未检测到显著DC偏移。接收信号均值为{rx_mean:.4f}，"
                f"在正常范围内(±{threshold:.4f})。"
            )
            diagnosis['suggested_threshold'] = 0.0

        return diagnosis

    def run_simulation(self, n_bits: int, eb_n0_db: float,
                       sample_size: int = 1000) -> dict:
        """
        运行完整BPSK通信仿真

        Args:
            n_bits: 仿真比特数
            eb_n0_db: Eb/N0 (dB)
            sample_size: 用于可视化的接收样本数量（避免返回全部数据）

        Returns:
            仿真结果字典
        """
        if n_bits <= 0:
            raise ValueError("n_bits must be positive")

        # B09修复：验证 sample_size 是正整数，拒绝 bool/浮点数/非正数
        if isinstance(sample_size, bool) or isinstance(sample_size, np.bool_):
            raise ValueError("sample_size must be an integer (bool not supported)")
        if not isinstance(sample_size, (int, np.integer)):
            raise ValueError("sample_size must be an integer")
        if sample_size <= 0:
            raise ValueError("sample_size must be a positive integer")

        # 生成并调制
        tx_bits = self.generate_bits(n_bits)
        tx_symbols = self.modulate_bpsk(tx_bits)

        # 信道传输
        rx_signals = self.add_awgn(tx_symbols, eb_n0_db)

        # 解调
        rx_bits = self.demodulate_bpsk(rx_signals)

        # 计算BER
        ber_theoretical = self.calculate_ber_theoretical(eb_n0_db)
        ber_measured, n_errors = self.calculate_ber_measured(tx_bits, rx_bits)

        # 返回有限样本用于可视化
        sample_count = min(sample_size, n_bits)

        return {
            'eb_n0_db': eb_n0_db,
            'n_bits': n_bits,
            'n_errors': n_errors,
            'ber_theoretical': float(ber_theoretical),
            'ber_measured': float(ber_measured),
            'seed': self.seed,
            'rx_samples': rx_signals[:sample_count].tolist(),
            'tx_symbols_samples': tx_symbols[:sample_count].tolist(),
        }

    def run_fault_diagnosis_experiment(self, n_bits: int, eb_n0_db: float,
                                       dc_offset: float = 0.0,
                                       sample_size: int = 1000) -> dict:
        """
        运行故障诊断实验（配对实验，保证同一批数据）

        Args:
            n_bits: 仿真比特数
            eb_n0_db: Eb/N0 (dB)
            dc_offset: DC偏移值
            sample_size: 用于可视化的接收样本数量

        Returns:
            完整的实验结果，包含正常、故障和测量数据
        """
        # C组修复 + B07修复：安全转换并验证数值参数（处理超大整数、object等）
        if n_bits <= 0:
            raise ValueError("n_bits must be positive")

        # 使用安全转换处理 eb_n0_db 和 dc_offset，防止超大整数泄漏 TypeError
        eb_n0_db = self._safe_scalar_to_float(eb_n0_db, "eb_n0_db")
        dc_offset = self._safe_scalar_to_float(dc_offset, "dc_offset")

        # B09修复：验证 sample_size 是正整数，拒绝 bool/浮点数/非正数
        if isinstance(sample_size, bool) or isinstance(sample_size, np.bool_):
            raise ValueError("sample_size must be an integer (bool not supported)")
        if not isinstance(sample_size, (int, np.integer)):
            raise ValueError("sample_size must be an integer")
        if sample_size <= 0:
            raise ValueError("sample_size must be a positive integer")

        # === 第一步：生成固定的发送数据和噪声 ===
        tx_bits = self.generate_bits(n_bits)
        tx_symbols = self.modulate_bpsk(tx_bits)

        # AUD4-03修复：使用数学稳定的公式计算噪声参数
        # 稳定公式: noise_std = sqrt(1/2) * 10^(-Eb/N0_dB/20)
        try:
            noise_std = np.sqrt(0.5) * (10.0 ** (-eb_n0_db / 20.0))

            # 验证结果有限且为正
            if not np.isfinite(noise_std):
                raise ValueError(f"Computed noise_std is not finite for eb_n0_db={eb_n0_db}")
            if noise_std <= 0:
                raise ValueError(f"Computed noise_std is not positive for eb_n0_db={eb_n0_db}")

        except (OverflowError, FloatingPointError) as e:
            raise ValueError(f"eb_n0_db={eb_n0_db} exceeds computational range") from e

        # 生成固定噪声
        noise = self.rng.normal(0, noise_std, size=tx_symbols.shape)

        # === 第二步：计算正常无故障状态 ===
        rx_normal = tx_symbols + noise
        rx_bits_normal = self.demodulate_bpsk(rx_normal)
        ber_normal, n_errors_normal = self.calculate_ber_measured(tx_bits, rx_bits_normal)

        # === 第三步：注入DC偏移故障 ===
        rx_with_fault = rx_normal + dc_offset  # 使用相同的发送符号和噪声
        rx_bits_with_fault = self.demodulate_bpsk(rx_with_fault)
        ber_with_fault, n_errors_with_fault = self.calculate_ber_measured(
            tx_bits, rx_bits_with_fault
        )

        # === 第四步：执行测量和诊断 ===
        rx_mean = self.calculate_rx_mean(rx_with_fault)
        diagnosis = self.diagnose_dc_offset(rx_mean, n_bits, noise_std)

        # === 第五步：初始修复（使用建议门限） ===
        suggested_threshold = diagnosis['suggested_threshold']
        rx_bits_repaired = self.demodulate_bpsk_with_threshold(
            rx_with_fault, suggested_threshold
        )
        ber_repaired, n_errors_repaired = self.calculate_ber_measured(
            tx_bits, rx_bits_repaired
        )

        # 返回有限样本用于可视化
        sample_count = min(sample_size, n_bits)

        # 计算理论BER（无故障情况）
        ber_theoretical = self.calculate_ber_theoretical(eb_n0_db)

        return {
            # 实验参数
            'eb_n0_db': eb_n0_db,
            'n_bits': n_bits,
            'dc_offset': float(dc_offset),
            'seed': self.seed,
            'noise_std': float(noise_std),

            # 正常无故障状态
            'normal': {
                'ber': float(ber_normal),
                'n_errors': int(n_errors_normal),
                'threshold': 0.0
            },

            # 故障注入后状态
            'with_fault': {
                'ber': float(ber_with_fault),
                'n_errors': int(n_errors_with_fault),
                'threshold': 0.0
            },

            # 测量与诊断
            'measurement': {
                'rx_mean': float(rx_mean),
                'noise_std': float(noise_std)
            },
            'diagnosis': diagnosis,

            # 修复后状态
            'repaired': {
                'ber': float(ber_repaired),
                'n_errors': int(n_errors_repaired),
                'threshold': float(suggested_threshold)
            },

            # 理论参考
            'ber_theoretical': float(ber_theoretical),

            # 可视化样本
            'samples': {
                'tx_symbols': tx_symbols[:sample_count].tolist(),
                'rx_normal': rx_normal[:sample_count].tolist(),
                'rx_with_fault': rx_with_fault[:sample_count].tolist()
            },

            # E组修复：返回完整数据用于API层缓存
            # 注意：此字段仅供API层使用，不应序列化返回给客户端
            '_tx_bits': tx_bits,
            '_rx_with_fault': rx_with_fault
        }

    def apply_custom_threshold(self, tx_bits: np.ndarray, rx_signals: np.ndarray,
                               threshold: float) -> dict:
        """
        应用自定义判决门限并重新判决

        Args:
            tx_bits: 发送比特（用于计算BER）
            rx_signals: 接收信号
            threshold: 判决门限

        Returns:
            判决结果字典

        Raises:
            ValueError: 门限或接收信号包含非有限值、为空或为复数
        """
        # P2-03修复：安全转换 threshold（防止大整数/complex/object TypeError）
        threshold = self._safe_scalar_to_float(threshold, "threshold")

        # P2-02修复：验证接收信号 dtype
        rx_array = np.asarray(rx_signals)
        if rx_array.size == 0:
            raise ValueError("rx_signals cannot be empty")

        # P2-5修复：验证接收信号为实数，包括object数组
        if np.iscomplexobj(rx_array) or rx_array.dtype == object:
            raise ValueError("rx_signals must be real-valued (complex numbers not supported)")

        # Round6修复：拒绝非实数dtype（字符串等）
        if rx_array.dtype.kind not in ('i', 'u', 'f', 'b'):
            raise ValueError(f"rx_signals must have numeric dtype (got dtype={rx_array.dtype})")

        # P2修复：验证接收信号有限性
        if not np.all(np.isfinite(rx_array)):
            raise ValueError("rx_signals must contain only finite values (not NaN or Infinity)")

        # AUD3-01修复：验证发送比特
        tx_array = np.asarray(tx_bits)
        if tx_array.size == 0:
            raise ValueError("tx_bits cannot be empty")

        # AUD4-02修复 + B07修复：拒绝complex和object dtype（在asarray之后，在isfinite之前）
        if np.iscomplexobj(tx_array) or tx_array.dtype == object:
            raise ValueError("tx_bits must be real-valued (complex dtype and object dtype not supported)")

        # Round6修复：拒绝非实数dtype（字符串等）
        if tx_array.dtype.kind not in ('i', 'u', 'f', 'b'):
            raise ValueError(f"tx_bits must have numeric dtype (got dtype={tx_array.dtype})")

        # 验证发送比特不包含非有限值
        if not np.all(np.isfinite(tx_array)):
            raise ValueError("tx_bits must contain only finite values (not NaN or Infinity)")

        # 验证发送比特为0/1
        if not np.all((tx_array == 0) | (tx_array == 1)):
            raise ValueError("tx_bits must contain only 0 or 1")

        rx_bits = self.demodulate_bpsk_with_threshold(rx_array, threshold)
        ber, n_errors = self.calculate_ber_measured(tx_array, rx_bits)

        return {
            'ber': float(ber),
            'n_errors': int(n_errors),
            'threshold': float(threshold)
        }
