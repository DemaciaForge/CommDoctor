"""
F03/F04精确边界测试 - 持久化测试套件

F03: 递归非有限数值检测
F04: 严格dtype白名单验证
"""

import pytest
import numpy as np
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app
from bpsk_simulator import BPSKSimulator


class TestF03RecursiveNonFiniteCheck:
    """F03: 递归检查JSON中所有嵌套的非有限数值"""

    def setup_method(self):
        self.client = TestClient(app)

    @pytest.mark.parametrize("test_case,payload,expected_status,error_keyword", [
        # 根级非有限值
        ("root_infinity", '{"eb_n0_db": 1e309, "n_bits": 10000}', 422, "finite"),
        ("root_neg_infinity", '{"eb_n0_db": -1e309, "n_bits": 10000}', 422, "finite"),

        # seed字段非有限值
        ("seed_infinity", '{"eb_n0_db": 8, "n_bits": 10000, "seed": 1e309}', 422, "finite"),
        ("seed_string", '{"eb_n0_db": 8, "n_bits": 10000, "seed": "invalid"}', 422, None),

        # sample_size字段非有限值
        ("sample_size_infinity", '{"eb_n0_db": 8, "n_bits": 10000, "sample_size": 1e309}', 422, "finite"),

        # eb_n0_db字段非有限值
        ("eb_n0_db_infinity", '{"eb_n0_db": 1e309, "n_bits": 10000}', 422, "finite"),

        # n_bits字段非有限值
        ("n_bits_infinity", '{"eb_n0_db": 8, "n_bits": 1e309}', 422, "finite"),

        # 嵌套对象中的非有限值
        ("nested_object_inf", '{"eb_n0_db": 8, "n_bits": 10000, "metadata": {"value": 1e309}}', 422, "finite"),

        # 嵌套数组中的Infinity
        ("nested_array_inf", '{"eb_n0_db": 8, "n_bits": 10000, "values": [1, 2, 1e309]}', 422, "finite"),

        # 整个请求体null
        ("body_null", 'null', 422, "must be a JSON object"),

        # 非法JSON
        ("invalid_json", '{invalid', 422, None),

        # 正常合法请求
        ("valid_request", '{"eb_n0_db": 8, "n_bits": 10000, "seed": 42}', 200, None),

        # 嵌套null是合法的（API忽略额外字段）
        ("nested_null_allowed", '{"eb_n0_db": 8, "n_bits": 10000, "metadata": {"value": null}}', 200, None),
    ])
    def test_nonfinite_detection(self, test_case, payload, expected_status, error_keyword):
        """参数化测试：检测各种位置的非有限数值"""
        response = self.client.post(
            "/api/simulate",
            content=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == expected_status, \
            f"Test case '{test_case}' failed: expected {expected_status}, got {response.status_code}"

        if expected_status == 422 and error_keyword:
            detail = response.json().get("detail", [])
            assert any(error_keyword.lower() in str(d).lower() for d in detail), \
                f"Expected keyword '{error_keyword}' in error detail for test case '{test_case}'"

    def test_string_nan_not_rejected(self):
        """字符串"NaN"应由Pydantic契约验证，不应被误判为浮点NaN"""
        # 字符串类型的seed会被Pydantic拒绝，但不应被中间件误判为float NaN
        response = self.client.post(
            "/api/simulate",
            json={"eb_n0_db": 8, "n_bits": 10000, "seed": "NaN"}
        )
        # 应该是类型错误，不是非有限值错误
        assert response.status_code == 422
        detail = response.json()["detail"]
        # 确保错误不是因为"finite"检查
        error_messages = " ".join(str(d) for d in detail)
        assert "finite" not in error_messages.lower()

    def test_valid_edge_values(self):
        """测试边界但合法的数值"""
        valid_cases = [
            {"eb_n0_db": -10, "n_bits": 100},  # 最小值
            {"eb_n0_db": 30, "n_bits": 1000000},  # 最大值
            {"eb_n0_db": 0, "n_bits": 10000, "seed": 0},  # 零值
            {"eb_n0_db": 8.5, "n_bits": 10000, "sample_size": 5000},  # 浮点数
        ]

        for case in valid_cases:
            response = self.client.post("/api/simulate", json=case)
            assert response.status_code == 200, f"Valid case rejected: {case}"


class TestF04StrictDtypeWhitelist:
    """F04: 严格dtype白名单 - 只接受i/u/b kind"""

    def setup_method(self):
        self.sim = BPSKSimulator(seed=42)

    @pytest.mark.parametrize("test_case,bits_factory,should_pass", [
        # 合法类型
        ("python_list", lambda: [0, 1, 0, 1], True),
        ("int32", lambda: np.array([0, 1, 0, 1], dtype=np.int32), True),
        ("int64", lambda: np.array([0, 1, 0, 1], dtype=np.int64), True),
        ("int8", lambda: np.array([0, 1, 0, 1], dtype=np.int8), True),
        ("uint8", lambda: np.array([0, 1, 0, 1], dtype=np.uint8), True),
        ("uint64", lambda: np.array([0, 1, 0, 1], dtype=np.uint64), True),
        ("bool", lambda: np.array([False, True, False, True], dtype=bool), True),

        # 非法类型 - float
        ("float_0_1", lambda: np.array([0.0, 1.0], dtype=np.float64), False),
        ("float32", lambda: np.array([0.0, 1.0], dtype=np.float32), False),

        # 非法类型 - complex
        ("complex", lambda: np.array([0+0j, 1+0j], dtype=np.complex128), False),

        # 非法类型 - object
        ("object", lambda: np.array([0, 1], dtype=object), False),

        # 非法类型 - string
        ("unicode", lambda: np.array(['0', '1'], dtype=np.str_), False),

        # 非法类型 - datetime64
        ("datetime64_D", lambda: np.array(['2020-01-01', '2020-01-02'], dtype='datetime64[D]'), False),
        ("datetime64_s", lambda: np.array(['2020-01-01', '2020-01-02'], dtype='datetime64[s]'), False),

        # 非法类型 - timedelta64
        ("timedelta64_D", lambda: np.array([0, 1], dtype='timedelta64[D]'), False),
        ("timedelta64_h", lambda: np.array([0, 1], dtype='timedelta64[h]'), False),

        # 非法类型 - 结构化数组
        ("structured_single", lambda: np.array([(0,), (1,)], dtype=[('f0', 'i4')]), False),
        ("structured_multi", lambda: np.array([(0, 1), (1, 0)], dtype=[('a', 'i4'), ('b', 'i4')]), False),
    ])
    def test_dtype_whitelist(self, test_case, bits_factory, should_pass):
        """参数化测试：dtype白名单验证"""
        bits = bits_factory()

        if should_pass:
            try:
                result = self.sim.modulate_bpsk(bits)
                # 验证结果正确
                assert len(result) == len(bits)
                assert np.all(np.isin(result, [-1, 1]))
            except ValueError as e:
                pytest.fail(f"Test case '{test_case}' should pass but raised: {e}")
        else:
            with pytest.raises(ValueError) as exc_info:
                self.sim.modulate_bpsk(bits)
            # 验证错误消息有意义
            error_msg = str(exc_info.value).lower()
            assert any(keyword in error_msg for keyword in
                      ['not supported', 'not allowed', 'unsupported dtype', 'must be']), \
                f"Test case '{test_case}' error message unclear: {exc_info.value}"

    @pytest.mark.parametrize("invalid_value,dtype", [
        # 整数类型中的非二进制值
        (2, np.int32),
        (-1, np.int32),
        (255, np.uint8),
        (1000, np.int64),
        # 大整数（超出int32但在int64/uint64内）
        (2**32, np.int64),
        (2**63 - 1, np.int64),
    ])
    def test_nonbinary_integer_rejection(self, invalid_value, dtype):
        """测试非二进制整数被拒绝"""
        bits = np.array([0, 1, invalid_value, 1], dtype=dtype)
        with pytest.raises(ValueError, match="must contain only 0 or 1"):
            self.sim.modulate_bpsk(bits)

    def test_mixed_bool_int_accepted(self):
        """测试混合布尔/整数数组（NumPy会自动统一类型）"""
        # Python列表混合bool/int会被NumPy转换为统一的整数类型
        bits = np.array([True, 0, False, 1])
        result = self.sim.modulate_bpsk(bits)
        expected = np.array([1, -1, -1, 1])
        np.testing.assert_array_equal(result, expected)

    def test_uint64_overflow_prevention(self):
        """测试uint64超大值不能通过溢出逃避检查"""
        # 使用uint64最大值，应被拒绝
        bits = np.array([0, 1, 2**64 - 1], dtype=np.uint64)
        with pytest.raises(ValueError, match="must contain only 0 or 1"):
            self.sim.modulate_bpsk(bits)

    def test_normal_bpsk_unchanged(self):
        """测试修复后正常BPSK计算结果不变"""
        bits = np.array([0, 1, 0, 1, 1, 0], dtype=np.int32)
        symbols = self.sim.modulate_bpsk(bits)
        expected = np.array([-1, 1, -1, 1, 1, -1])
        np.testing.assert_array_equal(symbols, expected)

        # 测试完整仿真流程
        result = self.sim.run_simulation(n_bits=10000, eb_n0_db=8, sample_size=100)
        assert result['n_bits'] == 10000
        assert len(result['rx_samples']) == 100
        assert 0 <= result['ber_measured'] <= 1


class TestF03RuntimeErrorPreservation:
    """F03要求：真实内部RuntimeError必须仍然是5xx"""

    def setup_method(self):
        # 使用raise_server_exceptions=False以便检查500状态码
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_internal_error_still_500(self):
        """验证内部逻辑错误仍返回500而非422"""
        # 使用mock在run_simulation方法中注入RuntimeError
        with patch('bpsk_simulator.BPSKSimulator.run_simulation') as mock_run:
            # 配置mock抛出RuntimeError
            mock_run.side_effect = RuntimeError("Simulated internal error")

            # 发送合法请求（参数验证应该通过）
            response = self.client.post(
                "/api/simulate",
                json={"eb_n0_db": 8, "n_bits": 10000, "seed": 42}
            )

            # 验证mock被调用（确保进入了仿真逻辑）
            assert mock_run.called, "run_simulation should have been called"

            # 严格断言返回500
            assert response.status_code == 500, \
                f"Internal RuntimeError should return 500, got {response.status_code}"

            # 验证响应包含错误信息
            detail = response.json()
            assert "detail" in detail
            assert "error" in detail["detail"].lower() or "simulation" in detail["detail"].lower()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
