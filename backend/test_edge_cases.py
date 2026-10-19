"""
F03和F04回归测试

F03: 测试完整请求体为null及其他边界情况
F04: 测试BPSK输入类型严格验证
"""

import pytest
import numpy as np
from fastapi.testclient import TestClient
from main import app
from bpsk_simulator import BPSKSimulator


class TestF03RequestBodyValidation:
    """F03: 请求体验证边界测试"""

    def setup_method(self):
        self.client = TestClient(app)

    def test_body_is_null(self):
        """测试完整请求体为null"""
        response = self.client.post(
            "/api/simulate",
            content="null",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail[0]["type"] == "type_error"
        assert "must be a JSON object" in detail[0]["msg"]

    def test_body_is_array(self):
        """测试完整请求体为数组"""
        response = self.client.post(
            "/api/simulate",
            content="[1, 2, 3]",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_field_is_null(self):
        """测试字段为null"""
        response = self.client.post(
            "/api/simulate",
            json={"eb_n0_db": None, "n_bits": 10000}
        )
        assert response.status_code == 422

    def test_missing_required_field(self):
        """测试缺失必需字段"""
        response = self.client.post(
            "/api/simulate",
            json={"eb_n0_db": 8}
        )
        assert response.status_code == 422

    def test_wrong_field_type(self):
        """测试字段类型错误"""
        response = self.client.post(
            "/api/simulate",
            json={"eb_n0_db": "not_a_number", "n_bits": 10000}
        )
        assert response.status_code == 422

    def test_infinity_value(self):
        """测试Infinity值"""
        response = self.client.post(
            "/api/simulate",
            content='{"eb_n0_db": 1e309, "n_bits": 10000}',
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("finite" in d["msg"].lower() for d in detail)

    def test_invalid_json(self):
        """测试非法JSON"""
        response = self.client.post(
            "/api/simulate",
            content="{invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_valid_request(self):
        """测试正常有效请求"""
        response = self.client.post(
            "/api/simulate",
            json={"eb_n0_db": 8, "n_bits": 10000, "seed": 42}
        )
        assert response.status_code == 200
        data = response.json()
        assert "ber_theoretical" in data
        assert "ber_measured" in data


class TestF04InputTypeValidation:
    """F04: BPSK输入类型严格验证"""

    def setup_method(self):
        self.sim = BPSKSimulator(seed=42)

    def test_accept_int_array(self):
        """接受整数数组"""
        bits = np.array([0, 1, 0, 1], dtype=np.int32)
        result = self.sim.modulate_bpsk(bits)
        assert np.array_equal(result, [-1, 1, -1, 1])

    def test_accept_bool_array(self):
        """接受布尔数组"""
        bits = np.array([False, True, False, True])
        result = self.sim.modulate_bpsk(bits)
        assert np.array_equal(result, [-1, 1, -1, 1])

    def test_accept_float_integers(self):
        """拒绝浮点形式的整数（0.0, 1.0）- F04修复后应拒绝所有float"""
        bits = np.array([0.0, 1.0, 0.0, 1.0])
        with pytest.raises(ValueError, match="Float inputs not allowed"):
            self.sim.modulate_bpsk(bits)

    def test_reject_float_decimals(self):
        """拒绝浮点小数"""
        bits = np.array([0.0, 0.5, 1.0, 1.5])
        with pytest.raises(ValueError, match="Float inputs not allowed"):
            self.sim.modulate_bpsk(bits)

    def test_reject_complex(self):
        """拒绝复数"""
        bits = np.array([0+0j, 1+0j])
        with pytest.raises(ValueError, match="Complex numbers are not supported"):
            self.sim.modulate_bpsk(bits)

    def test_reject_object_dtype(self):
        """拒绝object类型数组"""
        bits = np.array([0.0, 1.0], dtype=object)
        with pytest.raises(ValueError, match="Object dtype arrays are not supported"):
            self.sim.modulate_bpsk(bits)

    def test_reject_nan(self):
        """拒绝NaN"""
        bits = np.array([0.0, np.nan, 1.0])
        with pytest.raises(ValueError, match="Float inputs not allowed"):
            self.sim.modulate_bpsk(bits)

    def test_reject_infinity(self):
        """拒绝Infinity"""
        bits = np.array([0.0, np.inf, 1.0])
        with pytest.raises(ValueError, match="Float inputs not allowed"):
            self.sim.modulate_bpsk(bits)

    def test_reject_non_binary_int(self):
        """拒绝非0/1整数"""
        bits = np.array([0, 1, 2, 3])
        with pytest.raises(ValueError, match="must contain only 0 or 1"):
            self.sim.modulate_bpsk(bits)

    def test_reject_non_binary_float(self):
        """拒绝非0/1浮点数"""
        bits = np.array([0.0, 1.0, 2.0])
        with pytest.raises(ValueError, match="Float inputs not allowed"):
            self.sim.modulate_bpsk(bits)
