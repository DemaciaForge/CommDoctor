"""
Stage02 P2-F01至P2-F04问题的回归测试

这些测试锁定Codex独立审计发现的四类核心问题：
- P2-F01: 三个底层入口接受空数组
- P2-F02: Eb/N0=4000时理论BER路径泄漏OverflowError
- P2-F03: complex Eb/N0被放行并丢弃虚部
- P2-F04: NumPy整数回绕导致诊断翻转和DC加法变号
"""

import pytest
import numpy as np
from bpsk_simulator import BPSKSimulator


class TestP2F01EmptyArrayRejection:
    """P2-F01: 三个底层入口必须拒绝空数组"""

    def test_demodulate_bpsk_rejects_empty(self):
        """demodulate_bpsk必须拒绝空数组"""
        sim = BPSKSimulator(42)
        with pytest.raises(ValueError, match="received signal cannot be empty"):
            sim.demodulate_bpsk(np.array([]))

    def test_add_awgn_rejects_empty(self):
        """add_awgn必须拒绝空符号序列"""
        sim = BPSKSimulator(42)
        with pytest.raises(ValueError, match="symbols cannot be empty"):
            sim.add_awgn(np.array([]), 10.0)

    def test_add_dc_offset_rejects_empty(self):
        """add_dc_offset必须拒绝空信号"""
        sim = BPSKSimulator(42)
        with pytest.raises(ValueError, match="signals cannot be empty"):
            sim.add_dc_offset(np.array([]), 0.8)

    def test_minimal_legal_input_works(self):
        """确保单元素输入正常工作"""
        sim = BPSKSimulator(42)

        # 单元素解调
        result = sim.demodulate_bpsk(np.array([0.5]))
        assert result.shape == (1,)
        assert result[0] == 1

        # 单元素AWGN
        result = sim.add_awgn(np.array([-1.0]), 10.0)
        assert result.shape == (1,)
        assert np.isfinite(result[0])

        # 单元素DC
        result = sim.add_dc_offset(np.array([1.0]), 0.5)
        assert result.shape == (1,)
        assert abs(result[0] - 1.5) < 1e-10


class TestP2F02NoRawOverflow:
    """P2-F02: Eb/N0极值不能泄漏raw OverflowError"""

    def test_calculate_ber_theoretical_4000(self):
        """理论BER在4000 dB不能泄漏OverflowError"""
        sim = BPSKSimulator(42)
        # 旧代码：10**(4000/10)=10^400溢出
        # 新代码：10**(4000/20)=10^200可表示
        try:
            ber = sim.calculate_ber_theoretical(4000.0)
            # 如果可以计算，必须是有限值
            assert np.isfinite(ber)
            assert 0 <= ber <= 1
        except ValueError:
            # 或者明确拒绝，但不能是OverflowError
            pass

    def test_run_simulation_4000(self):
        """run_simulation在4000 dB不能泄漏OverflowError"""
        sim = BPSKSimulator(42)
        try:
            result = sim.run_simulation(100, 4000.0)
            assert 'ber_theoretical' in result
            assert np.isfinite(result['ber_theoretical'])
        except ValueError:
            pass

    def test_run_fault_diagnosis_4000(self):
        """故障诊断在4000 dB不能泄漏OverflowError"""
        sim = BPSKSimulator(42)
        try:
            result = sim.run_fault_diagnosis_experiment(100, 4000.0, 0.8)
            assert 'ber_theoretical' in result
            assert np.isfinite(result['ber_theoretical'])
        except ValueError:
            pass

    def test_extreme_overflow_converts_to_valueerror(self):
        """确实无法表示的值应该转换为ValueError"""
        sim = BPSKSimulator(42)
        with pytest.raises(ValueError, match="exceeds computational range"):
            sim.calculate_ber_theoretical(10000.0)


class TestP2F03ComplexEbN0Rejection:
    """P2-F03: complex Eb/N0必须被拒绝，包括零虚部"""

    @pytest.mark.parametrize("complex_val", [
        1+2j,
        1+0j,
        np.complex64(1+2j),
        np.complex64(1+0j),
        np.complex128(1+2j),
        np.complex128(1+0j),
    ])
    def test_add_awgn_rejects_complex_eb_n0(self, complex_val):
        """add_awgn必须拒绝所有形式的complex Eb/N0"""
        sim = BPSKSimulator(42)
        with pytest.raises(ValueError, match="eb_n0_db must be real-valued"):
            sim.add_awgn(np.array([-1., 1.]), complex_val)

    @pytest.mark.parametrize("complex_val", [
        1+2j,
        1+0j,
        np.complex64(1+2j),
        np.complex64(1+0j),
        np.complex128(1+2j),
        np.complex128(1+0j),
    ])
    def test_calculate_ber_theoretical_rejects_complex(self, complex_val):
        """理论BER必须拒绝所有形式的complex Eb/N0"""
        sim = BPSKSimulator(42)
        with pytest.raises(ValueError, match="eb_n0_db must be real-valued"):
            sim.calculate_ber_theoretical(complex_val)

    @pytest.mark.parametrize("complex_val", [
        1+2j,
        1+0j,
    ])
    def test_run_simulation_rejects_complex(self, complex_val):
        """run_simulation必须拒绝complex Eb/N0"""
        sim = BPSKSimulator(42)
        with pytest.raises(ValueError, match="eb_n0_db must be real-valued"):
            sim.run_simulation(100, complex_val)

    def test_zero_imaginary_part_still_rejected(self):
        """即使虚部为0，complex类型仍应被拒绝"""
        sim = BPSKSimulator(42)

        # Python complex
        with pytest.raises(ValueError):
            sim.add_awgn(np.array([1.0]), 1+0j)

        # NumPy complex
        with pytest.raises(ValueError):
            sim.calculate_ber_theoretical(np.complex128(1+0j))


class TestP2F04IntegerWraparound:
    """P2-F04: NumPy整数类型不能静默回绕"""

    def test_diagnose_int64_vs_float_consistency(self):
        """同一数值的int64和float应得到一致的诊断结果"""
        sim = BPSKSimulator(42)

        # 2**32的平方会导致int64回绕为0
        value_int = np.int64(2**32)
        value_float = float(2**32)

        result_int = sim.diagnose_dc_offset(0.5, 100, value_int)
        result_float = sim.diagnose_dc_offset(0.5, 100, value_float)

        # 两种dtype应得到相同的诊断
        assert result_int['has_dc_offset'] == result_float['has_dc_offset'], \
            f"int64 gave {result_int['has_dc_offset']}, float gave {result_float['has_dc_offset']}"

        # std_error应该相近（同一数值）
        assert abs(result_int['evidence']['std_error'] -
                   result_float['evidence']['std_error']) < 1e6

    def test_add_dc_offset_no_wraparound(self):
        """add_dc_offset在整数输入时不能回绕为负数"""
        sim = BPSKSimulator(42)

        max_int64 = np.iinfo(np.int64).max
        result = sim.add_dc_offset(np.array([max_int64]), 1)

        # 结果必须是正数，不能回绕为负
        assert result[0] > 0, f"Expected positive, got {result[0]}"

        # 应该接近max_int64 + 1
        expected = float(max_int64) + 1.0
        assert abs(result[0] - expected) < 1e3  # 允许浮点误差

    def test_integer_signal_converted_safely(self):
        """整数信号应被安全转换以避免加法回绕"""
        sim = BPSKSimulator(42)

        # 使用较大的int64值
        large_val = np.int64(10**15)
        signal = np.array([large_val])

        result = sim.add_dc_offset(signal, 1.0)

        # 结果类型应该是float
        assert result.dtype == np.float64
        # 结果应该正确
        assert result[0] == float(large_val) + 1.0
