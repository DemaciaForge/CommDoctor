"""
Round6 独立审计回归测试

测试原始 12 项失败输入，确保：
1. 非法输入被正确拒绝（不泄漏 TypeError）
2. 合法输入继续工作
3. 变异后的代码会被这些测试检测到

本测试文件由 Round7 创建，专门覆盖 Round6 独立审计报告第 3 节的全部原始输入。
"""

import pytest
import numpy as np
from fastapi.testclient import TestClient
from bpsk_simulator import BPSKSimulator
from main import app


class TestRound6ScalarTypeValidation:
    """测试标量类型校验（原始失败 1-4）"""

    def setup_method(self):
        self.simulator = BPSKSimulator(seed=42)

    def test_string_threshold_rejected(self):
        """原始失败 1: 字符串门限 '0.5'，精确原始输入 np.ones(2)"""
        with pytest.raises(ValueError, match="numeric, not string"):
            self.simulator.demodulate_bpsk_with_threshold(np.ones(2), '0.5')

    def test_object_dtype_threshold_rejected(self):
        """原始失败 2: object dtype 零维门限，精确原始输入 np.ones(2)"""
        threshold = np.array(0.5, dtype=object)
        with pytest.raises(ValueError, match="object dtype"):
            self.simulator.demodulate_bpsk_with_threshold(np.ones(2), threshold)

    def test_string_eb_n0_rejected(self):
        """原始失败 3: 字符串 Eb/N0 '10'"""
        with pytest.raises(ValueError, match="numeric, not string"):
            self.simulator.run_fault_diagnosis_experiment(
                n_bits=100, eb_n0_db='10', dc_offset=0.8
            )

    def test_string_dc_offset_rejected(self):
        """原始失败 4: 字符串 DC offset '0.8'"""
        with pytest.raises(ValueError, match="numeric, not string"):
            self.simulator.run_fault_diagnosis_experiment(
                n_bits=100, eb_n0_db=10, dc_offset='0.8'
            )


class TestRound6ArrayTypeValidation:
    """测试数组类型校验（原始失败 5-6）

    Round8 修复：补充精确原始输入测试
    """

    def setup_method(self):
        self.simulator = BPSKSimulator(seed=42)

    def test_unicode_tx_bits_rejected(self):
        """原始失败 5: Unicode 发送比特数组"""
        tx_bits = np.array(['0', '1', '0', '1'], dtype='U1')
        with pytest.raises(ValueError, match="numeric dtype"):
            self.simulator.apply_custom_threshold(
                tx_bits=tx_bits,
                rx_signals=np.array([1, -1, 1, -1]),
                threshold=0.5
            )

    def test_unicode_rx_signals_rejected(self):
        """原始失败 6: Unicode 接收信号数组"""
        rx_signals = np.array(['1', '-1', '1', '-1'], dtype='U2')
        with pytest.raises(ValueError, match="numeric dtype"):
            self.simulator.demodulate_bpsk_with_threshold(rx_signals, 0.5)

    def test_original_case5_exact_input(self):
        """原始失败 5 的精确原样输入

        原始调用：
        S(42).apply_custom_threshold(
            np.array(['0','1']),  # 2元素 U1
            np.array([-1.,1.]),   # 2元素 float64
            0                     # threshold=0
        )
        """
        s = BPSKSimulator(42)
        a = np.array(['0', '1'])  # 原始 2 元素 Unicode
        with pytest.raises(ValueError, match="numeric dtype"):
            s.apply_custom_threshold(a, np.array([-1., 1.]), 0)

    def test_original_case6_exact_input(self):
        """原始失败 6 的精确原样输入

        原始调用：
        S(42).demodulate_bpsk_with_threshold(
            np.array(['0','1']),  # 2元素 U1
            0                     # threshold=0
        )
        """
        s = BPSKSimulator(42)
        a = np.array(['0', '1'])  # 原始 2 元素 Unicode
        with pytest.raises(ValueError, match="numeric dtype"):
            s.demodulate_bpsk_with_threshold(a, 0)


class TestRound6NumPyIntegerLimits:
    """测试 NumPy 整数上限（原始失败 7-8）

    Round8 修复：采用方案 B，取消任意固定上限。
    10^16 现在应该被接受（只要能安全计算标准误差）。
    """

    def setup_method(self):
        self.simulator = BPSKSimulator(seed=42)

    def test_np_int64_10_power_16_accepted(self):
        """原始失败 7: np.int64(10**16) - Round8 改为接受"""
        n_samples = np.int64(10**16)
        result = self.simulator.diagnose_dc_offset(
            rx_mean=0.1, n_samples=n_samples, noise_std=0.5
        )

        # 验证结果合法
        assert result['evidence']['n_samples'] == 10**16
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0

    def test_np_uint64_10_power_16_accepted(self):
        """原始失败 8: np.uint64(10**16) - Round8 改为接受"""
        n_samples = np.uint64(10**16)
        result = self.simulator.diagnose_dc_offset(
            rx_mean=0.1, n_samples=n_samples, noise_std=0.5
        )

        # 验证结果合法
        assert result['evidence']['n_samples'] == 10**16
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0


class TestRound6APISampleSizeCoercion:
    """测试 API sample_size 强制转换（原始失败 9-12）

    Round8 修复：增加 spy 验证，证明非法请求在计算前被拒绝
    """

    def setup_method(self):
        self.client = TestClient(app)

    def test_simulate_float_sample_size_rejected(self, monkeypatch):
        """原始失败 9: /api/simulate 的 sample_size=100.0"""
        # Spy 验证拒绝发生在计算前
        from unittest.mock import MagicMock
        from bpsk_simulator import BPSKSimulator

        run_simulation_spy = MagicMock()
        monkeypatch.setattr(BPSKSimulator, 'run_simulation', run_simulation_spy)

        response = self.client.post(
            "/api/simulate",
            json={
                "n_bits": 100,
                "eb_n0_db": 10.0,
                "sample_size": 100.0,  # float 而非 int
                "seed": 42
            }
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("sample_size" in str(err).lower() for err in detail)

        # 验证 run_simulation 未被调用
        assert run_simulation_spy.call_count == 0

    def test_fault_diagnosis_float_sample_size_rejected(self, monkeypatch):
        """原始失败 10: /api/fault-diagnosis 的 sample_size=100.0"""
        from unittest.mock import MagicMock
        from bpsk_simulator import BPSKSimulator

        run_fault_diagnosis_spy = MagicMock()
        monkeypatch.setattr(BPSKSimulator, 'run_fault_diagnosis_experiment', run_fault_diagnosis_spy)

        response = self.client.post(
            "/api/fault-diagnosis",
            json={
                "n_bits": 100,
                "eb_n0_db": 10.0,
                "dc_offset": 0.8,
                "sample_size": 100.0,
                "seed": 42
            }
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("sample_size" in str(err).lower() for err in detail)

        # 验证 run_fault_diagnosis_experiment 未被调用
        assert run_fault_diagnosis_spy.call_count == 0

    def test_simulate_string_sample_size_rejected(self, monkeypatch):
        """原始失败 11: /api/simulate 的 sample_size="100" """
        from unittest.mock import MagicMock
        from bpsk_simulator import BPSKSimulator

        run_simulation_spy = MagicMock()
        monkeypatch.setattr(BPSKSimulator, 'run_simulation', run_simulation_spy)

        response = self.client.post(
            "/api/simulate",
            json={
                "n_bits": 100,
                "eb_n0_db": 10.0,
                "sample_size": "100",  # 字符串而非 int
                "seed": 42
            }
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("sample_size" in str(err).lower() for err in detail)

        # 验证 run_simulation 未被调用
        assert run_simulation_spy.call_count == 0

    def test_fault_diagnosis_string_sample_size_rejected(self, monkeypatch):
        """原始失败 12: /api/fault-diagnosis 的 sample_size="100" """
        from unittest.mock import MagicMock
        from bpsk_simulator import BPSKSimulator

        run_fault_diagnosis_spy = MagicMock()
        monkeypatch.setattr(BPSKSimulator, 'run_fault_diagnosis_experiment', run_fault_diagnosis_spy)

        response = self.client.post(
            "/api/fault-diagnosis",
            json={
                "n_bits": 100,
                "eb_n0_db": 10.0,
                "dc_offset": 0.8,
                "sample_size": "100",
                "seed": 42
            }
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("sample_size" in str(err).lower() for err in detail)

        # 验证 run_fault_diagnosis_experiment 未被调用
        assert run_fault_diagnosis_spy.call_count == 0


class TestRound6LegitimateInputs:
    """验证合法输入继续工作"""

    def setup_method(self):
        self.simulator = BPSKSimulator(seed=42)
        self.client = TestClient(app)

    def test_legitimate_scalar_inputs(self):
        """合法标量输入"""
        # Python int/float
        result1 = self.simulator.run_fault_diagnosis_experiment(
            n_bits=100, eb_n0_db=10, dc_offset=0.8
        )
        assert result1["with_fault"]["n_errors"] > 0

        # NumPy scalars
        result2 = self.simulator.run_fault_diagnosis_experiment(
            n_bits=100, eb_n0_db=np.float64(10.0), dc_offset=np.float32(0.8)
        )
        assert result2["with_fault"]["n_errors"] > 0

    def test_legitimate_array_inputs(self):
        """合法数组输入"""
        tx_bits = np.array([0, 1, 0, 1], dtype=np.int32)
        # BPSK mapping: 0->-1, 1->+1
        # 创建无噪声的接收信号
        rx_signals = np.array([-1.0, 1.0, -1.0, 1.0], dtype=np.float64)

        result = self.simulator.apply_custom_threshold(
            tx_bits=tx_bits, rx_signals=rx_signals, threshold=0.0
        )
        # 应该全部正确（0 errors）
        assert result["n_errors"] == 0

    def test_legitimate_n_samples(self):
        """合法 n_samples（包括大值但在安全范围内）"""
        # Python int
        result1 = self.simulator.diagnose_dc_offset(0.1, 10**15, 0.5)
        assert np.isfinite(result1["evidence"]["std_error"])

        # np.int64
        result2 = self.simulator.diagnose_dc_offset(0.1, np.int64(10**15), 0.5)
        assert np.isfinite(result2["evidence"]["std_error"])

        # np.uint64
        result3 = self.simulator.diagnose_dc_offset(0.1, np.uint64(10**15), 0.5)
        assert np.isfinite(result3["evidence"]["std_error"])

    def test_legitimate_api_requests(self):
        """合法 API 请求"""
        response = self.client.post(
            "/api/simulate",
            json={
                "n_bits": 100,
                "eb_n0_db": 10.0,
                "sample_size": 100,  # 真正的整数
                "seed": 42
            }
        )
        assert response.status_code == 200
        assert response.json()["n_errors"] >= 0


class TestRound7BytesTypeValidation:
    """Round7 新增：bytes 类型校验"""

    def setup_method(self):
        self.simulator = BPSKSimulator(seed=42)

    def test_bytes_threshold_rejected(self):
        """bytes 门限"""
        with pytest.raises(ValueError, match="numeric, not bytes"):
            self.simulator.demodulate_bpsk_with_threshold([1, -1], b'0.5')

    def test_np_bytes_threshold_rejected(self):
        """np.bytes_ 门限"""
        with pytest.raises(ValueError, match="numeric, not bytes"):
            self.simulator.demodulate_bpsk_with_threshold([1, -1], np.bytes_(b'0.5'))

    def test_bytes_array_threshold_rejected(self):
        """bytes 零维数组门限"""
        threshold = np.array(b'0.5')
        with pytest.raises(ValueError, match="numeric, not bytes"):
            self.simulator.demodulate_bpsk_with_threshold([1, -1], threshold)

    def test_bytes_eb_n0_rejected(self):
        """bytes Eb/N0"""
        with pytest.raises(ValueError, match="numeric, not bytes"):
            self.simulator.run_fault_diagnosis_experiment(
                n_bits=100, eb_n0_db=b'10', dc_offset=0.8
            )


class TestRound7CalculateRxMeanTypeError:
    """Round7 新增：calculate_rx_mean TypeError 修复"""

    def setup_method(self):
        self.simulator = BPSKSimulator(seed=42)

    def test_unicode_array_rejected(self):
        """Unicode 数组不泄漏 TypeError"""
        with pytest.raises(ValueError, match="numeric dtype"):
            self.simulator.calculate_rx_mean(np.array(['0', '1']))

    def test_bytes_array_rejected(self):
        """bytes 数组不泄漏 TypeError"""
        with pytest.raises(ValueError, match="numeric dtype"):
            self.simulator.calculate_rx_mean(np.array([b'0', b'1']))

    def test_valid_array_works(self):
        """合法数组正常工作"""
        result = self.simulator.calculate_rx_mean([1.0, -1.0, 0.5])
        assert np.isfinite(result)
