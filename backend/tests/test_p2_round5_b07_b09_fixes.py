"""
Stage02 P2 第五轮修复：B07 和 B09 正式回归测试

根据独立审计报告 STAGE02_P2_ROUND4_FINAL_AUDIT.md 中确认仍失败的输入
"""
import pytest
import numpy as np
from bpsk_simulator import BPSKSimulator


class TestB07ObjectAndLargeIntegerFixes:
    """B07: object数组和超大整数泄漏 TypeError"""

    def test_apply_custom_threshold_rejects_object_dtype_tx(self):
        """apply_custom_threshold 必须拒绝 object dtype tx数组"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match=r"tx_bits.*(object dtype|real-valued)"):
            S.apply_custom_threshold(
                np.array([0j, 1+0j], dtype=object),
                np.array([-1., 1.]),
                0.
            )

    def test_demodulate_bpsk_with_threshold_rejects_huge_int_threshold(self):
        """demodulate_bpsk_with_threshold 必须拒绝超大整数门限"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match=r"threshold.*cannot be converted"):
            S.demodulate_bpsk_with_threshold(np.ones(2), 10**400)

    def test_run_fault_diagnosis_rejects_huge_int_eb_n0_db(self):
        """run_fault_diagnosis_experiment 必须拒绝超大整数 eb_n0_db"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match=r"eb_n0_db.*cannot be converted"):
            S.run_fault_diagnosis_experiment(100, 10**400, 0.8)

    def test_run_fault_diagnosis_rejects_huge_int_dc_offset(self):
        """run_fault_diagnosis_experiment 必须拒绝超大整数 dc_offset"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match=r"dc_offset.*cannot be converted"):
            S.run_fault_diagnosis_experiment(100, 10, 10**400)

    def test_apply_custom_threshold_accepts_valid_int_threshold(self):
        """合法整数门限应该正常工作"""
        S = BPSKSimulator(42)
        tx = np.array([0, 1, 0, 1])
        rx = np.array([-1.0, 1.0, -0.5, 0.5])
        result = S.apply_custom_threshold(tx, rx, 0.0)
        assert 'ber' in result
        assert 0 <= result['ber'] <= 1

    def test_demodulate_threshold_accepts_large_but_valid_int(self):
        """可表示的大整数（如 2**63-1）应该正常工作"""
        S = BPSKSimulator(42)
        rx = np.array([1.0, -1.0])
        # 2**63-1 可以安全转换为 float64
        result = S.demodulate_bpsk_with_threshold(rx, 2**63-1)
        assert isinstance(result, np.ndarray)
        assert len(result) == 2


class TestB09SampleSizeValidation:
    """B09: sample_size 参数验证缺失"""

    def test_run_simulation_rejects_negative_sample_size(self):
        """run_simulation 必须拒绝负数 sample_size"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match=r"sample_size must be.*positive"):
            S.run_simulation(100, 10, sample_size=-1)

    def test_run_simulation_rejects_zero_sample_size(self):
        """run_simulation 必须拒绝零 sample_size"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match=r"sample_size must be.*positive"):
            S.run_simulation(100, 10, sample_size=0)

    def test_run_simulation_rejects_bool_sample_size(self):
        """run_simulation 必须拒绝 bool 类型（不能把 True 当作 1）"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match=r"bool not supported"):
            S.run_simulation(100, 10, sample_size=True)

        with pytest.raises(ValueError, match=r"bool not supported"):
            S.run_simulation(100, 10, sample_size=False)

    def test_run_simulation_rejects_numpy_bool(self):
        """run_simulation 必须拒绝 NumPy bool 类型"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match=r"bool not supported"):
            S.run_simulation(100, 10, sample_size=np.bool_(True))

    def test_run_simulation_rejects_float_sample_size(self):
        """run_simulation 必须拒绝浮点数 sample_size"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match=r"must be an integer"):
            S.run_simulation(100, 10, sample_size=1.5)

        with pytest.raises(ValueError, match=r"must be an integer"):
            S.run_simulation(100, 10, sample_size=100.0)

    def test_run_fault_diagnosis_rejects_bool_sample_size(self):
        """run_fault_diagnosis_experiment 必须拒绝 bool sample_size"""
        S = BPSKSimulator(42)
        with pytest.raises(ValueError, match=r"bool not supported"):
            S.run_fault_diagnosis_experiment(100, 10, 0.8, sample_size=True)

    def test_run_simulation_accepts_valid_positive_int(self):
        """合法正整数 sample_size 应该正常工作"""
        S = BPSKSimulator(42)
        result = S.run_simulation(100, 10, sample_size=50)
        assert len(result['rx_samples']) == 50
        assert result['n_bits'] == 100

    def test_run_simulation_accepts_numpy_int_types(self):
        """NumPy 整数类型应该被接受"""
        S = BPSKSimulator(42)

        result1 = S.run_simulation(100, 10, sample_size=np.int32(30))
        assert len(result1['rx_samples']) == 30

        result2 = S.run_simulation(100, 10, sample_size=np.int64(40))
        assert len(result2['rx_samples']) == 40

        result3 = S.run_simulation(100, 10, sample_size=np.uint64(20))
        assert len(result3['rx_samples']) == 20

    def test_run_simulation_clips_sample_size_to_n_bits(self):
        """sample_size 超过 n_bits 应该被截断为 n_bits"""
        S = BPSKSimulator(42)
        result = S.run_simulation(100, 10, sample_size=500)
        assert len(result['rx_samples']) == 100  # 被截断为 n_bits

    def test_run_fault_diagnosis_accepts_valid_sample_size(self):
        """run_fault_diagnosis_experiment 应该接受合法的 sample_size"""
        S = BPSKSimulator(42)
        result = S.run_fault_diagnosis_experiment(100, 10, 0.8, sample_size=30)
        assert len(result['samples']['rx_normal']) == 30
        assert len(result['samples']['rx_with_fault']) == 30


class TestB07B09RegressionProtection:
    """确保修复不破坏已有的合法行为"""

    def test_diagnose_dc_offset_still_accepts_large_valid_int(self):
        """diagnose_dc_offset 仍然接受可表示的大整数"""
        S = BPSKSimulator(42)
        # 2**63-1 是可以安全转换为 float64 的
        result = S.diagnose_dc_offset(0.5, 100, 2**63-1)
        assert 'has_dc_offset' in result
        assert 'evidence' in result

    def test_apply_threshold_normal_behavior_unchanged(self):
        """apply_custom_threshold 的正常行为保持不变"""
        S = BPSKSimulator(42)
        tx = np.array([0, 1, 0, 1, 1])
        rx = np.array([-1.2, 0.8, -0.3, 1.1, 0.7])

        result = S.apply_custom_threshold(tx, rx, 0.0)
        # 用门限0解调：rx>0 => [0,1,0,1,1] 与 tx 完全匹配
        assert result['ber'] == 0.0
        assert result['n_errors'] == 0
        assert result['threshold'] == 0.0

        # 用不合适的门限会产生错误
        result2 = S.apply_custom_threshold(tx, rx, 1.0)
        assert result2['ber'] > 0  # 门限过高会导致错误

    def test_fault_diagnosis_normal_eb_n0_unchanged(self):
        """故障诊断实验对正常 Eb/N0 的行为不变"""
        S = BPSKSimulator(42)
        result = S.run_fault_diagnosis_experiment(
            n_bits=1000,
            eb_n0_db=10,
            dc_offset=0.8,
            sample_size=100
        )

        assert result['normal']['ber'] < result['with_fault']['ber']
        assert len(result['samples']['rx_normal']) == 100
        assert 'diagnosis' in result
