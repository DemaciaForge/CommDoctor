"""
B07 和 B09 缺陷复现回归测试
根据独立审计报告 STAGE02_P2_ROUND4_FINAL_AUDIT.md

将历史缺陷输入转为正式回归测试，带明确断言。
"""
import pytest
import numpy as np
from bpsk_simulator import BPSKSimulator


class TestB07ObjectDtypeAndLargeIntegers:
    """B07: object dtype 和大整数必须被正确拒绝"""

    def test_apply_custom_threshold_rejects_object_dtype_tx(self):
        """B07-1: apply_custom_threshold 必须拒绝 object dtype 发送信号"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match="object dtype"):
            S.apply_custom_threshold(
                np.array([0j, 1+0j], dtype=object),
                np.array([-1., 1.]),
                0.
            )

    def test_demodulate_bpsk_with_threshold_rejects_huge_threshold(self):
        """B07-2: demodulate_bpsk_with_threshold 必须拒绝超大整数门限"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match="(finite|range|overflow|too large|cannot be converted)"):
            S.demodulate_bpsk_with_threshold(np.ones(2), 10**400)

    def test_run_fault_diagnosis_experiment_rejects_huge_eb_n0(self):
        """B07-3: run_fault_diagnosis_experiment 必须拒绝超大整数 Eb/N0"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match="(finite|range|overflow|too large|cannot be converted)"):
            S.run_fault_diagnosis_experiment(100, 10**400, 0.8)

    def test_run_fault_diagnosis_experiment_rejects_huge_dc_offset(self):
        """B07-4: run_fault_diagnosis_experiment 必须拒绝超大整数 DC 偏移"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match="(finite|range|overflow|too large|cannot be converted)"):
            S.run_fault_diagnosis_experiment(100, 10, 10**400)


class TestB09SampleSizeValidation:
    """B09: sample_size 参数必须拒绝非法值"""

    def test_run_simulation_rejects_negative_sample_size(self):
        """B09-1: run_simulation 必须拒绝负数 sample_size"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match="(sample_size|positive|negative)"):
            S.run_simulation(100, 10, sample_size=-1)

    def test_run_simulation_rejects_zero_sample_size(self):
        """B09-2: run_simulation 必须拒绝零 sample_size"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match="(sample_size|positive|zero)"):
            S.run_simulation(100, 10, sample_size=0)

    def test_run_simulation_rejects_bool_sample_size(self):
        """B09-3: run_simulation 必须拒绝 bool sample_size"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match="(sample_size|bool|integer)"):
            S.run_simulation(100, 10, sample_size=True)

    def test_run_simulation_rejects_float_sample_size(self):
        """B09-4: run_simulation 必须拒绝浮点数 sample_size"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match="(sample_size|float|integer)"):
            S.run_simulation(100, 10, sample_size=1.5)

    def test_run_fault_diagnosis_experiment_rejects_bool_sample_size(self):
        """B09-5: run_fault_diagnosis_experiment 必须拒绝 bool sample_size"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match="(sample_size|bool|integer)"):
            S.run_fault_diagnosis_experiment(100, 10, 0.8, sample_size=True)


class TestB07B09RegressionSmoke:
    """合法输入的冒烟测试，确保修复没有破坏正常功能"""

    def test_apply_custom_threshold_with_valid_inputs(self):
        """确保 apply_custom_threshold 正常输入仍然工作"""
        S = BPSKSimulator(42)
        # apply_custom_threshold 要求 tx_bits 为整数比特 (0/1)
        tx = np.array([0, 1, 0, 1], dtype=np.int32)
        rx = np.array([-1., 1., -0.5, 1.5], dtype=np.float64)
        result = S.apply_custom_threshold(tx, rx, 0.0)
        assert result is not None
        assert 'n_errors' in result

    def test_run_simulation_with_valid_sample_size(self):
        """确保 run_simulation 正常 sample_size 仍然工作"""
        S = BPSKSimulator(42)
        result = S.run_simulation(100, 10, sample_size=50)
        assert len(result['rx_samples']) == 50
        assert result['n_errors'] >= 0

    def test_run_fault_diagnosis_experiment_with_valid_inputs(self):
        """确保 run_fault_diagnosis_experiment 正常输入仍然工作"""
        S = BPSKSimulator(42)
        result = S.run_fault_diagnosis_experiment(100, 10, 0.8, sample_size=50)
        assert 'samples' in result
        assert 'diagnosis' in result
        assert len(result['samples']['rx_normal']) == 50
