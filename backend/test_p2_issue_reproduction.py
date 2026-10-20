"""
P2 问题复现回归测试
根据独立审计报告中的四个 P2 问题

将历史复现输入转为正式回归测试，带明确断言。
"""
import pytest
import numpy as np
from fastapi.testclient import TestClient
from main import app
from bpsk_simulator import BPSKSimulator


class TestP2Issue01ContentType:
    """P2-01: Content-Type 错误必须返回 422 而非 415"""

    def test_text_plain_returns_422_not_415(self):
        """text/plain Content-Type 必须返回 422"""
        client = TestClient(app)
        response = client.post(
            "/api/simulate",
            content='{"n_bits":100,"eb_n0_db":10,"seed":42,"sample_size":100}',
            headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 422, f"期望 422，实际 {response.status_code}"
        assert response.headers["Content-Type"] == "application/json"
        data = response.json()
        assert "detail" in data


class TestP2Issue02ObjectDtype:
    """P2-02: object dtype 必须抛出 ValueError 而非泄漏 TypeError"""

    def test_demodulate_bpsk_rejects_object_dtype_with_valueerror(self):
        """demodulate_bpsk 必须对 object dtype 抛出 ValueError"""
        with pytest.raises(ValueError, match="object dtype"):
            BPSKSimulator(42).demodulate_bpsk(np.array([0j, 1+0j], dtype=object))


class TestP2Issue03NumPyIntegerWraparound:
    """P2-03: NumPy 整数类型 Eb/N0 不能导致回绕"""

    def test_uint8_eb_n0_matches_float(self):
        """np.uint8(10) 必须与 10.0 产生相同结果"""
        result_float = BPSKSimulator(42).run_simulation(10000, 10.0)['n_errors']
        result_uint8 = BPSKSimulator(42).run_simulation(10000, np.uint8(10))['n_errors']
        assert result_float == result_uint8, \
            f"np.uint8(10) 产生 {result_uint8} 错误，而 10.0 产生 {result_float} 错误"

    def test_int8_negative_eb_n0_matches_float(self):
        """np.int8(-128) 必须与 -128.0 产生相同结果"""
        result_float = BPSKSimulator(42).run_simulation(10000, -128.0)['n_errors']
        result_int8 = BPSKSimulator(42).run_simulation(10000, np.int8(-128))['n_errors']
        assert result_float == result_int8, \
            f"np.int8(-128) 产生 {result_int8} 错误，而 -128.0 产生 {result_float} 错误"


class TestP2Issue04SampleSizeValidation:
    """P2-04: sample_size 必须拒绝非法值"""

    def test_negative_sample_size_rejected(self):
        """sample_size=-1 必须被拒绝"""
        with pytest.raises(ValueError, match="(sample_size|positive|negative)"):
            BPSKSimulator(42).run_simulation(100, 10, sample_size=-1)

    def test_zero_sample_size_rejected(self):
        """sample_size=0 必须被拒绝"""
        with pytest.raises(ValueError, match="(sample_size|positive|zero)"):
            BPSKSimulator(42).run_simulation(100, 10, sample_size=0)

    def test_bool_sample_size_rejected(self):
        """sample_size=True 必须被拒绝"""
        with pytest.raises(ValueError, match="(sample_size|bool|integer)"):
            BPSKSimulator(42).run_simulation(100, 10, sample_size=True)

    def test_float_sample_size_rejected(self):
        """sample_size=1.5 必须被拒绝"""
        with pytest.raises(ValueError, match="(sample_size|float|integer)"):
            BPSKSimulator(42).run_simulation(100, 10, sample_size=1.5)
