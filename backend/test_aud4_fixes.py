"""
AUD4 修复回归测试

测试 AUD4-01、AUD4-02、AUD4-03 的修复
"""
import numpy as np
import pytest

from bpsk_simulator import BPSKSimulator


class TestAUD401NonFiniteInputs:
    """AUD4-01: 非有限值必须被所有数学入口拒绝"""

    def test_demodulate_bpsk_rejects_nan(self):
        """demodulate_bpsk 必须拒绝 NaN"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.demodulate_bpsk(np.array([1.0, np.nan]))

    def test_demodulate_bpsk_rejects_positive_inf(self):
        """demodulate_bpsk 必须拒绝 +Infinity"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.demodulate_bpsk(np.array([1.0, np.inf]))

    def test_demodulate_bpsk_rejects_negative_inf(self):
        """demodulate_bpsk 必须拒绝 -Infinity"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.demodulate_bpsk(np.array([1.0, -np.inf]))

    def test_add_awgn_rejects_nan_signal(self):
        """add_awgn 必须拒绝包含 NaN 的信号"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.add_awgn(np.array([1.0, np.nan]), 10.0)

    def test_add_awgn_rejects_inf_signal(self):
        """add_awgn 必须拒绝包含 Infinity 的信号"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.add_awgn(np.array([1.0, np.inf]), 10.0)
        with pytest.raises(ValueError, match="finite"):
            s.add_awgn(np.array([1.0, -np.inf]), 10.0)

    def test_add_awgn_rejects_nan_eb_n0(self):
        """add_awgn 必须拒绝 NaN Eb/N0"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.add_awgn(np.array([1.0, -1.0]), np.nan)

    def test_add_awgn_rejects_inf_eb_n0(self):
        """add_awgn 必须拒绝 Infinity Eb/N0"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.add_awgn(np.array([1.0, -1.0]), np.inf)
        with pytest.raises(ValueError, match="finite"):
            s.add_awgn(np.array([1.0, -1.0]), -np.inf)

    def test_calculate_ber_theoretical_rejects_nan(self):
        """calculate_ber_theoretical 必须拒绝 NaN Eb/N0"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.calculate_ber_theoretical(np.nan)

    def test_calculate_ber_theoretical_rejects_inf(self):
        """calculate_ber_theoretical 必须拒绝 Infinity Eb/N0"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.calculate_ber_theoretical(np.inf)
        with pytest.raises(ValueError, match="finite"):
            s.calculate_ber_theoretical(-np.inf)

    def test_run_simulation_rejects_nan_eb_n0(self):
        """run_simulation 必须拒绝 NaN Eb/N0"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.run_simulation(100, np.nan)

    def test_run_simulation_rejects_inf_eb_n0(self):
        """run_simulation 必须拒绝 Infinity Eb/N0"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="finite"):
            s.run_simulation(100, np.inf)


class TestAUD402ComplexDtypeRejection:
    """AUD4-02: 所有 bit 入口必须拒绝 complex dtype（即使虚部为0）"""

    def test_calculate_ber_rejects_complex_tx_zero_imag(self):
        """BER 必须拒绝零虚部的 complex tx"""
        s = BPSKSimulator(42)
        tx = np.array([0+0j, 1+0j])
        rx = np.array([0, 1])
        with pytest.raises(ValueError, match="real-valued|complex"):
            s.calculate_ber_measured(tx, rx)

    def test_calculate_ber_rejects_complex_rx_zero_imag(self):
        """BER 必须拒绝零虚部的 complex rx"""
        s = BPSKSimulator(42)
        tx = np.array([0, 1])
        rx = np.array([0+0j, 1+0j])
        with pytest.raises(ValueError, match="real-valued|complex"):
            s.calculate_ber_measured(tx, rx)

    def test_calculate_ber_rejects_complex64(self):
        """BER 必须拒绝 np.complex64 dtype"""
        s = BPSKSimulator(42)
        tx = np.array([0, 1], dtype=np.complex64)
        rx = np.array([0, 1])
        with pytest.raises(ValueError, match="real-valued|complex"):
            s.calculate_ber_measured(tx, rx)

    def test_calculate_ber_rejects_complex128(self):
        """BER 必须拒绝 np.complex128 dtype"""
        s = BPSKSimulator(42)
        tx = np.array([0, 1], dtype=np.complex128)
        rx = np.array([0, 1])
        with pytest.raises(ValueError, match="real-valued|complex"):
            s.calculate_ber_measured(tx, rx)

    def test_calculate_ber_rejects_complex_nonzero_imag(self):
        """BER 必须拒绝非零虚部的 complex"""
        s = BPSKSimulator(42)
        tx = np.array([0+1j, 1+0j])
        rx = np.array([0, 1])
        with pytest.raises(ValueError, match="real-valued|complex"):
            s.calculate_ber_measured(tx, rx)

    def test_apply_threshold_rejects_complex_tx_zero_imag(self):
        """apply_custom_threshold 必须拒绝零虚部的 complex tx"""
        s = BPSKSimulator(42)
        tx = np.array([0+0j, 1+0j])
        signal = np.array([-1.0, 1.0])
        with pytest.raises(ValueError, match="real-valued|complex"):
            s.apply_custom_threshold(tx, signal, 0.0)

    def test_apply_threshold_rejects_complex64_tx(self):
        """apply_custom_threshold 必须拒绝 np.complex64 tx"""
        s = BPSKSimulator(42)
        tx = np.array([0, 1], dtype=np.complex64)
        signal = np.array([-1.0, 1.0])
        with pytest.raises(ValueError, match="real-valued|complex"):
            s.apply_custom_threshold(tx, signal, 0.0)

    def test_apply_threshold_rejects_complex128_tx(self):
        """apply_custom_threshold 必须拒绝 np.complex128 tx"""
        s = BPSKSimulator(42)
        tx = np.array([0, 1], dtype=np.complex128)
        signal = np.array([-1.0, 1.0])
        with pytest.raises(ValueError, match="real-valued|complex"):
            s.apply_custom_threshold(tx, signal, 0.0)


class TestAUD403EbN0OverflowStability:
    """AUD4-03: Eb/N0 极端值必须使用稳定算法或明确拒绝"""

    def test_extreme_positive_eb_n0_3080(self):
        """Eb/N0=3080 dB 必须产生正确的极小 noise_std"""
        s = BPSKSimulator(42)
        result = s.run_fault_diagnosis_experiment(100, 3080.0, 0.8)

        noise_std = result['noise_std']

        # 验证 noise_std 有限且为正
        assert np.isfinite(noise_std), f"noise_std must be finite, got {noise_std}"
        assert noise_std > 0, f"noise_std must be positive, got {noise_std}"

        # 验证 noise_std 不是错误的 0
        assert noise_std != 0.0, "noise_std must not be zero (overflow artifact)"

        # 期望值约为 7.07e-155
        # 使用相对容差验证
        expected = 7.071067811865476e-155
        rel_tol = 1e-12
        assert abs(noise_std - expected) / expected < rel_tol, \
            f"noise_std={noise_std}, expected≈{expected}"

    def test_extreme_negative_eb_n0_minus_3080(self):
        """Eb/N0=-3080 dB 必须产生有限的极大 noise_std"""
        s = BPSKSimulator(42)
        result = s.run_fault_diagnosis_experiment(100, -3080.0, 0.8)

        noise_std = result['noise_std']

        # 验证 noise_std 有限且为正
        assert np.isfinite(noise_std), f"noise_std must be finite, got {noise_std}"
        assert noise_std > 0, f"noise_std must be positive, got {noise_std}"

    def test_diagnose_overflow_eb_n0_1e308(self):
        """Eb/N0=1e308 导致的溢出必须明确拒绝为 ValueError"""
        s = BPSKSimulator(42)

        # 这应该拒绝，而不是抛出 OverflowError
        with pytest.raises(ValueError, match="overflow|Variance"):
            s.diagnose_dc_offset(0.5, 100, 1e308)

    def test_normal_eb_n0_still_works(self):
        """正常范围的 Eb/N0 必须继续正常工作"""
        s = BPSKSimulator(42)

        # 测试正常范围：0, 5, 10, 15 dB
        for eb_n0 in [0.0, 5.0, 10.0, 15.0]:
            result = s.run_fault_diagnosis_experiment(100, eb_n0, 0.8)
            noise_std = result['noise_std']

            assert np.isfinite(noise_std)
            assert noise_std > 0

    def test_add_awgn_extreme_eb_n0_3080(self):
        """add_awgn 在极端 Eb/N0=3080 时必须产生有限输出"""
        s = BPSKSimulator(42)
        symbols = np.array([1.0, -1.0, 1.0, -1.0])

        result = s.add_awgn(symbols, 3080.0)

        # 验证输出有限
        assert np.all(np.isfinite(result)), "add_awgn output must be finite"

    def test_add_awgn_extreme_negative_eb_n0(self):
        """add_awgn 在极端负 Eb/N0 时必须产生有限输出"""
        s = BPSKSimulator(42)
        symbols = np.array([1.0, -1.0, 1.0, -1.0])

        result = s.add_awgn(symbols, -3080.0)

        # 验证输出有限
        assert np.all(np.isfinite(result)), "add_awgn output must be finite"


class TestAUD4Regression:
    """验证 AUD4 修复不破坏已有功能"""

    def test_aud3_02_empty_ber_still_fails(self):
        """AUD3-02: 空数组必须继续被拒绝"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="empty"):
            s.calculate_ber_measured(np.array([]), np.array([1]))

    def test_aud3_03_bool_n_samples_still_fails(self):
        """AUD3-03: bool n_samples 必须继续被拒绝"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="bool|integer"):
            s.diagnose_dc_offset(0.5, True, 0.1)

    def test_aud3_06_ber_broadcasting_still_fails(self):
        """AUD3-06: BER 广播必须继续被拒绝"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="length|shape"):
            s.calculate_ber_measured(
                np.array([0]),
                np.array([0, 1, 0])
            )

    def test_fixed_10db_experiment_still_accurate(self):
        """固定 10 dB 实验必须保持准确"""
        s = BPSKSimulator(42)
        result = s.run_fault_diagnosis_experiment(10000, 10.0, 0.8)

        # 验证 noise_std
        expected_noise_std = 0.22360679774997896
        assert abs(result['noise_std'] - expected_noise_std) < 1e-15

        # 验证故障误码
        assert result['with_fault']['n_errors'] == 962
        assert abs(result['with_fault']['ber'] - 0.0962) < 1e-10

        # 验证修复误码
        assert result['repaired']['n_errors'] == 0
        assert result['repaired']['ber'] == 0.0
