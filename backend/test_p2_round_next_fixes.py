"""
Stage02 P2 Round Next 修复测试
针对独立审计报告中发现的 8 个阻断问题
"""

import pytest
import numpy as np
from bpsk_simulator import BPSKSimulator
from fastapi.testclient import TestClient
from main import app


class TestB01ModulateEmptyArray:
    """B01: modulate_bpsk 空数组漏检"""

    def test_empty_int64_array_rejected(self):
        """空 int64 数组必须被拒绝"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="bits cannot be empty"):
            s.modulate_bpsk(np.array([], dtype=np.int64))

    def test_empty_bool_array_rejected(self):
        """空布尔数组必须被拒绝"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="bits cannot be empty"):
            s.modulate_bpsk(np.array([], dtype=bool))

    def test_empty_2d_array_rejected(self):
        """空二维数组必须被拒绝"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="bits cannot be empty"):
            s.modulate_bpsk(np.empty((2, 0), dtype=int))

    def test_empty_uint8_array_rejected(self):
        """空 uint8 数组必须被拒绝"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="bits cannot be empty"):
            s.modulate_bpsk(np.array([], dtype=np.uint8))


class TestB02DiagnoseIntegerWraparound:
    """B02: diagnose_dc_offset 整数回绕"""

    def test_int64_min_abs_no_wraparound(self):
        """int64 最小值必须正确诊断，不能因 abs 回绕而误判"""
        s = BPSKSimulator(42)
        rx_mean = np.int64(-(2**63))
        result = s.diagnose_dc_offset(rx_mean, 100, 0.1)
        # 极大负均值应该被检测为有 DC 偏移
        assert result['has_dc_offset'] is True

    def test_int32_min_abs_no_wraparound(self):
        """int32 最小值必须正确诊断"""
        s = BPSKSimulator(42)
        rx_mean = np.int32(-(2**31))
        result = s.diagnose_dc_offset(rx_mean, 100, 0.1)
        assert result['has_dc_offset'] is True

    def test_int16_min_abs_no_wraparound(self):
        """int16 最小值必须正确诊断"""
        s = BPSKSimulator(42)
        rx_mean = np.int16(-(2**15))
        result = s.diagnose_dc_offset(rx_mean, 100, 0.1)
        assert result['has_dc_offset'] is True

    def test_int8_min_abs_no_wraparound(self):
        """int8 最小值必须正确诊断"""
        s = BPSKSimulator(42)
        rx_mean = np.int8(-128)
        result = s.diagnose_dc_offset(rx_mean, 100, 0.1)
        assert result['has_dc_offset'] is True


class TestB03ObjectComplexBypass:
    """B03: calculate_ber_measured object complex 绕过"""

    def test_object_complex_zero_imaginary_tx_rejected(self):
        """object dtype 中零虚部 complex 必须被拒绝（tx_bits）"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="object dtype not supported"):
            s.calculate_ber_measured(
                np.array([0j, 1+0j], dtype=object),
                np.array([0, 1])
            )

    def test_object_complex_nonzero_imaginary_tx_rejected(self):
        """object dtype 中非零虚部 complex 必须被拒绝（tx_bits）"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="object dtype not supported"):
            s.calculate_ber_measured(
                np.array([1+2j], dtype=object),
                np.array([1])
            )

    def test_object_complex_zero_imaginary_rx_rejected(self):
        """object dtype 中零虚部 complex 必须被拒绝（rx_bits）"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="object dtype not supported"):
            s.calculate_ber_measured(
                np.array([0, 1]),
                np.array([0j, 1+0j], dtype=object)
            )

    def test_object_complex_nonzero_imaginary_rx_rejected(self):
        """object dtype 中非零虚部 complex 必须被拒绝（rx_bits）"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="object dtype not supported"):
            s.calculate_ber_measured(
                np.array([1]),
                np.array([1+2j], dtype=object)
            )


class TestB06AWGNOverflow:
    """B06: add_awgn 返回 Infinity"""

    def test_extreme_signal_plus_noise_overflow_rejected(self):
        """极值信号加噪声溢出必须被拒绝"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="overflow|non-finite"):
            s.add_awgn(np.full(10, 1.7e308), -6160.0)

    def test_finite_signal_returns_finite_result(self):
        """有限信号必须返回有限结果"""
        s = BPSKSimulator(42)
        result = s.add_awgn(np.array([1.0, -1.0]), 10.0)
        assert np.all(np.isfinite(result))


class TestB07BottomLayerTypeValidation:
    """B07: 底层类型验证"""

    def test_add_awgn_object_dtype_rejected(self):
        """add_awgn 必须拒绝 object dtype"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="object dtype"):
            s.add_awgn(np.array([1.0, -1.0], dtype=object), 10.0)

    def test_add_awgn_python_large_int_eb_n0_rejected(self):
        """add_awgn 必须拒绝 Python 超大整数 Eb/N0"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="(exceeds|cannot be converted|too large)"):
            s.add_awgn(np.array([1.0, -1.0]), 10**400)

    def test_theoretical_ber_python_large_int_eb_n0_rejected(self):
        """calculate_ber_theoretical 必须拒绝 Python 超大整数"""
        s = BPSKSimulator(42)
        with pytest.raises(ValueError, match="(exceeds|cannot be converted|too large)"):
            s.calculate_ber_theoretical(10**400)

    def test_diagnose_python_large_int_n_samples_accepted_when_computable(self):
        """diagnose_dc_offset 接受超大整数 n_samples（如果能产生有效标准误差）

        Round8 修复：采用方案 B，不再使用固定上限。
        10**400 能产生有效的标准误差，应被接受。
        """
        s = BPSKSimulator(42)
        result = s.diagnose_dc_offset(0.5, 10**400, 0.1)

        # 验证结果合法
        assert result['evidence']['n_samples'] == 10**400
        std_error = result['evidence']['std_error']
        assert np.isfinite(std_error)
        assert std_error > 0
        assert std_error < 1e-100  # 应该非常小


class TestB04B05APIErrorHandling:
    """B04/B05: API 错误处理"""

    def setup_method(self):
        """初始化测试客户端"""
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_wrong_content_type_returns_422_not_500(self):
        """错误 Content-Type 必须返回 422 (per project contract) 而非 500"""
        response = self.client.post(
            "/api/simulate",
            content='{"n_bits":100,"eb_n0_db":10,"seed":42,"sample_size":100}',
            headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["headers", "content-type"]

    def test_super_long_integer_returns_422_not_500(self):
        """超长整数必须返回 422 而非 500"""
        # 生成 4401 位整数
        long_int_json = '{"n_bits":' + '1' + '0' * 4400 + ',"eb_n0_db":10}'
        response = self.client.post(
            "/api/simulate",
            content=long_int_json,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_wrong_content_type_fault_diagnosis_returns_422(self):
        """fault-diagnosis 端点错误 Content-Type 必须返回 422"""
        response = self.client.post(
            "/api/fault-diagnosis",
            content='{"n_bits":100,"eb_n0_db":10,"dc_offset":0.8}',
            headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 422

    def test_wrong_content_type_apply_threshold_returns_422(self):
        """apply-threshold 端点错误 Content-Type 必须返回 422"""
        response = self.client.post(
            "/api/apply-threshold",
            content='{"experiment_id":"test","threshold":0.5}',
            headers={"Content-Type": "text/plain"}
        )
        # 即使 experiment_id 不存在，Content-Type 错误应该先被捕获为 422
        assert response.status_code == 422


class TestCounterfactualMutation:
    """反事实测试：验证测试确实能检测到 bug"""

    def test_modulate_empty_would_fail_without_fix(self):
        """如果没有空数组检查，这个测试会失败"""
        s = BPSKSimulator(42)
        # 当前实现：应该抛出 ValueError
        # 旧实现：会返回空数组
        with pytest.raises(ValueError, match="empty"):
            s.modulate_bpsk(np.array([], dtype=np.int64))

    def test_diagnose_int64_min_would_fail_without_fix(self):
        """如果没有整数转换，这个测试会失败"""
        s = BPSKSimulator(42)
        result = s.diagnose_dc_offset(np.int64(-(2**63)), 100, 0.1)
        # 当前实现：has_dc_offset 应该是 True
        # 旧实现：abs 回绕会导致 has_dc_offset 是 False
        assert result['has_dc_offset'] is True

    def test_object_complex_would_fail_without_fix(self):
        """如果没有 object dtype 检查，这个测试会失败"""
        s = BPSKSimulator(42)
        # 当前实现：应该抛出 ValueError
        # 旧实现：会静默接受并返回 (0.0, 0)
        with pytest.raises(ValueError, match="object dtype not supported"):
            s.calculate_ber_measured(
                np.array([0j, 1+0j], dtype=object),
                np.array([0, 1])
            )
