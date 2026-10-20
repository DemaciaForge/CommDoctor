"""
Stage02 P2 Round 4 修复的回归测试

覆盖四个问题：
- B04: Content-Type 返回 422（不是 415）
- B07: object dtype 和大整数拒绝
- B08: NumPy 整数 Eb/N0 回绕
- B09: sample_size 验证
"""

import pytest
import numpy as np
from fastapi.testclient import TestClient
import sys
import os

# 添加 backend 目录到 path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from bpsk_simulator import BPSKSimulator
from main import app


class TestP2Round4B04ContentType:
    """B04: Content-Type 必须返回 422（不是 415）"""

    def test_text_plain_returns_422(self):
        """text/plain Content-Type 必须返回 422"""
        client = TestClient(app)
        response = client.post(
            "/api/simulate",
            data='{"n_bits": 100, "eb_n0_db": 10.0, "seed": 42}',
            headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 422
        assert response.headers["Content-Type"] == "application/json"
        data = response.json()
        assert "detail" in data
        # detail 是一个列表，包含错误信息
        detail_str = str(data["detail"])
        assert "Content-Type" in detail_str or "content-type" in detail_str.lower()

    def test_application_xml_returns_422(self):
        """application/xml 必须返回 422"""
        client = TestClient(app)
        response = client.post(
            "/api/simulate",
            data='<xml>test</xml>',
            headers={"Content-Type": "application/xml"}
        )
        assert response.status_code == 422

    def test_correct_content_type_works(self):
        """正确的 application/json 应正常工作"""
        client = TestClient(app)
        response = client.post(
            "/api/simulate",
            json={"n_bits": 100, "eb_n0_db": 10.0, "seed": 42}
        )
        assert response.status_code == 200


class TestP2Round4B07ObjectDtype:
    """B07: object dtype 和大整数必须被拒绝"""

    def test_demodulate_bpsk_rejects_object_dtype(self):
        """demodulate_bpsk 必须拒绝 object dtype"""
        sim = BPSKSimulator(seed=42)
        signal = np.array([1.0, -1.0, 1.0], dtype=object)
        with pytest.raises(ValueError, match="object dtype"):
            sim.demodulate_bpsk(signal)

    def test_add_awgn_rejects_huge_eb_n0(self):
        """add_awgn 必须拒绝超大整数 Eb/N0"""
        sim = BPSKSimulator(seed=42)
        symbols = np.array([1.0, -1.0, 1.0], dtype=np.float64)
        huge_int = 10 ** 309
        with pytest.raises(ValueError, match="(finite|range|overflow|too large|cannot be converted)"):
            sim.add_awgn(symbols, huge_int)

    def test_calculate_ber_theoretical_rejects_huge_int(self):
        """calculate_ber_theoretical 必须拒绝超大整数"""
        sim = BPSKSimulator(seed=42)
        huge_int = 10 ** 309
        with pytest.raises(ValueError, match="(finite|range|overflow|too large|cannot be converted)"):
            sim.calculate_ber_theoretical(huge_int)

    def test_add_dc_offset_rejects_huge_offset(self):
        """add_dc_offset 必须拒绝超大 DC offset"""
        sim = BPSKSimulator(seed=42)
        symbols = np.array([1.0, -1.0], dtype=np.float64)
        huge_offset = 10 ** 309
        with pytest.raises(ValueError, match="(finite|range|overflow|too large|cannot be converted)"):
            sim.add_dc_offset(symbols, huge_offset)

    def test_apply_custom_threshold_rejects_huge_threshold(self):
        """apply_custom_threshold 必须拒绝超大门限"""
        sim = BPSKSimulator(seed=42)
        tx_bits = np.array([0, 1], dtype=np.uint8)
        rx_signals = np.array([0.5, -0.5], dtype=np.float64)
        huge_threshold = 10 ** 309
        with pytest.raises(ValueError, match="(finite|range|overflow|too large|cannot be converted)"):
            sim.apply_custom_threshold(tx_bits, rx_signals, huge_threshold)


class TestP2Round4B08NumPyIntegerWrapAround:
    """B08: NumPy 整数 Eb/N0 必须正确处理（不能回绕）"""

    def test_uint8_eb_n0_no_wrap_around(self):
        """np.uint8(10) 必须产生与 10.0 相同的结果"""
        bits = np.array([0, 1] * 5000, dtype=np.int32)

        # 使用 uint8
        sim1 = BPSKSimulator(seed=42)
        symbols1 = sim1.modulate_bpsk(bits)
        noisy1 = sim1.add_awgn(symbols1, np.uint8(10))
        rx1 = sim1.demodulate_bpsk(noisy1)
        errors_uint8 = int(np.sum(bits != rx1))

        # 使用 float
        sim2 = BPSKSimulator(seed=42)
        symbols2 = sim2.modulate_bpsk(bits)
        noisy2 = sim2.add_awgn(symbols2, 10.0)
        rx2 = sim2.demodulate_bpsk(noisy2)
        errors_float = int(np.sum(bits != rx2))

        # 结果必须一致
        assert errors_uint8 == errors_float, (
            f"uint8(10) produced {errors_uint8} errors, "
            f"but float(10.0) produced {errors_float} errors"
        )

    def test_int8_eb_n0_no_wrap_around(self):
        """np.int8(10) 必须产生与 10.0 相同的结果"""
        bits = np.array([0, 1] * 5000, dtype=np.int32)

        sim1 = BPSKSimulator(seed=42)
        symbols1 = sim1.modulate_bpsk(bits)
        noisy1 = sim1.add_awgn(symbols1, np.int8(10))
        rx1 = sim1.demodulate_bpsk(noisy1)
        errors_int8 = int(np.sum(bits != rx1))

        sim2 = BPSKSimulator(seed=42)
        symbols2 = sim2.modulate_bpsk(bits)
        noisy2 = sim2.add_awgn(symbols2, 10.0)
        rx2 = sim2.demodulate_bpsk(noisy2)
        errors_float = int(np.sum(bits != rx2))

        assert errors_int8 == errors_float

    def test_int64_eb_n0_works(self):
        """np.int64(10) 必须正常工作"""
        sim = BPSKSimulator(seed=42)
        bits = np.array([0, 1] * 100, dtype=np.int32)
        symbols = sim.modulate_bpsk(bits)
        noisy = sim.add_awgn(symbols, np.int64(10))
        rx_bits = sim.demodulate_bpsk(noisy)
        # 应该解码成功（不一定完全正确）
        assert len(rx_bits) == len(bits)

    def test_python_int_eb_n0_works(self):
        """Python int 必须正常工作"""
        sim = BPSKSimulator(seed=42)
        bits = np.array([0, 1] * 100, dtype=np.int32)
        symbols = sim.modulate_bpsk(bits)
        noisy = sim.add_awgn(symbols, 10)  # Python int
        rx_bits = sim.demodulate_bpsk(noisy)
        assert len(rx_bits) == len(bits)


class TestP2Round4B09SampleSizeValidation:
    """B09: sample_size 必须拒绝 bool、负数、零、非整数"""

    def test_diagnose_dc_offset_rejects_bool_true(self):
        """diagnose_dc_offset 必须拒绝 bool(True)"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="bool|integer"):
            sim.diagnose_dc_offset(0.5, True, 0.1)

    def test_diagnose_dc_offset_rejects_bool_false(self):
        """diagnose_dc_offset 必须拒绝 bool(False)"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="bool|integer|positive"):
            sim.diagnose_dc_offset(0.5, False, 0.1)

    def test_diagnose_dc_offset_rejects_zero(self):
        """diagnose_dc_offset 必须拒绝 sample_size=0"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="positive"):
            sim.diagnose_dc_offset(0.5, 0, 0.1)

    def test_diagnose_dc_offset_rejects_negative(self):
        """diagnose_dc_offset 必须拒绝负数"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="positive"):
            sim.diagnose_dc_offset(0.5, -100, 0.1)

    def test_diagnose_dc_offset_rejects_float(self):
        """diagnose_dc_offset 必须拒绝浮点数"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="integer"):
            sim.diagnose_dc_offset(0.5, 100.5, 0.1)

    def test_diagnose_dc_offset_accepts_valid_int(self):
        """diagnose_dc_offset 必须接受合法整数"""
        sim = BPSKSimulator(seed=42)
        result = sim.diagnose_dc_offset(0.5, 1000, 0.1)
        assert result is not None
        assert "has_dc_offset" in result
        assert "estimated_offset" in result

    def test_diagnose_dc_offset_accepts_numpy_int(self):
        """diagnose_dc_offset 必须接受 NumPy 整数"""
        sim = BPSKSimulator(seed=42)
        result = sim.diagnose_dc_offset(0.5, np.int64(1000), 0.1)
        assert result is not None


class TestP2Round4NormalInputRegression:
    """确保修复不影响正常输入"""

    def test_normal_simulation_still_works(self):
        """正常仿真必须仍然工作"""
        sim = BPSKSimulator(seed=42)
        bits = sim.generate_bits(1000)
        symbols = sim.modulate_bpsk(bits)
        noisy = sim.add_awgn(symbols, 10.0)
        rx_bits = sim.demodulate_bpsk(noisy)
        ber_measured, errors = sim.calculate_ber_measured(bits, rx_bits)
        ber_theoretical = sim.calculate_ber_theoretical(10.0)
        assert ber_theoretical > 0
        assert errors >= 0

    def test_dc_offset_diagnosis_still_works(self):
        """DC offset 诊断必须仍然工作"""
        sim = BPSKSimulator(seed=42)
        result = sim.diagnose_dc_offset(0.8, 10000, 0.1)
        assert result["has_dc_offset"] is True
        assert "suggested_threshold" in result
