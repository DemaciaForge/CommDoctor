"""
FastAPI接口测试

验证API端点的正确性和错误处理
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestAPI:
    """API测试类"""

    def test_root_endpoint(self):
        """测试根路径"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "CommDoctor API"
        assert data["status"] == "running"

    def test_health_check(self):
        """测试健康检查"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_simulation_valid_request(self):
        """测试有效的仿真请求"""
        request_data = {
            "eb_n0_db": 8.0,
            "n_bits": 10000,
            "seed": 42,
            "sample_size": 500
        }
        response = client.post("/api/simulate", json=request_data)
        assert response.status_code == 200

        data = response.json()
        # 验证必需字段
        assert "eb_n0_db" in data
        assert "n_bits" in data
        assert "n_errors" in data
        assert "ber_theoretical" in data
        assert "ber_measured" in data
        assert "rx_samples" in data
        assert "tx_symbols_samples" in data

        # 验证数据正确性
        assert data["eb_n0_db"] == 8.0
        assert data["n_bits"] == 10000
        assert data["seed"] == 42
        assert len(data["rx_samples"]) == 500
        assert len(data["tx_symbols_samples"]) == 500

    def test_simulation_reproducibility(self):
        """测试固定种子的可复现性"""
        request_data = {
            "eb_n0_db": 10.0,
            "n_bits": 5000,
            "seed": 123
        }

        response1 = client.post("/api/simulate", json=request_data)
        response2 = client.post("/api/simulate", json=request_data)

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        assert data1["n_errors"] == data2["n_errors"]
        assert data1["ber_measured"] == data2["ber_measured"]

    def test_simulation_no_seed(self):
        """测试不指定随机种子"""
        request_data = {
            "eb_n0_db": 5.0,
            "n_bits": 10000
        }
        response = client.post("/api/simulate", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["seed"] is None

    def test_simulation_invalid_eb_n0(self):
        """测试无效的Eb/N0参数"""
        request_data = {
            "eb_n0_db": 100.0,  # 超出范围
            "n_bits": 1000
        }
        response = client.post("/api/simulate", json=request_data)
        assert response.status_code == 422  # Validation error

    def test_simulation_invalid_n_bits(self):
        """测试无效的比特数"""
        request_data = {
            "eb_n0_db": 10.0,
            "n_bits": 50  # 小于最小值100
        }
        response = client.post("/api/simulate", json=request_data)
        assert response.status_code == 422

    def test_simulation_zero_n_bits(self):
        """测试零比特数"""
        request_data = {
            "eb_n0_db": 10.0,
            "n_bits": 0
        }
        response = client.post("/api/simulate", json=request_data)
        assert response.status_code == 422

    def test_simulation_missing_required_fields(self):
        """测试缺少必需字段"""
        request_data = {
            "eb_n0_db": 10.0
            # 缺少 n_bits
        }
        response = client.post("/api/simulate", json=request_data)
        assert response.status_code == 422

    def test_simulation_theoretical_ber_accuracy(self):
        """测试理论BER计算准确性"""
        request_data = {
            "eb_n0_db": 10.0,
            "n_bits": 10000,
            "seed": 42
        }
        response = client.post("/api/simulate", json=request_data)
        assert response.status_code == 200

        data = response.json()
        # 10dB的理论BER应该是 0.0000038721082
        expected_ber = 0.0000038721082
        assert abs(data["ber_theoretical"] - expected_ber) / expected_ber < 1e-6

    def test_simulation_infinity_eb_n0(self):
        """测试F03: 极端非法数值应返回422而非500"""
        # 使用字符串表示无穷大，避免JSON序列化问题
        import json
        json_data = '{"eb_n0_db": 1e309, "n_bits": 10000, "seed": 42}'
        response = client.post(
            "/api/simulate",
            content=json_data,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_simulation_nan_eb_n0(self):
        """测试F03: NaN应返回422而非500"""
        # 直接发送null来测试验证器
        json_data = '{"eb_n0_db": null, "n_bits": 10000, "seed": 42}'
        response = client.post(
            "/api/simulate",
            content=json_data,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_simulation_null_eb_n0(self):
        """测试F03第三轮: null值应返回422而非500"""
        response = client.post("/api/simulate", json={
            "eb_n0_db": None,
            "n_bits": 10000,
            "seed": 42
        })
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_simulation_string_eb_n0(self):
        """测试F03第三轮: 字符串类型应返回422而非500"""
        response = client.post("/api/simulate", json={
            "eb_n0_db": "invalid",
            "n_bits": 10000,
            "seed": 42
        })
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_simulation_missing_eb_n0(self):
        """测试F03第三轮: 缺失必需字段应返回422而非500"""
        response = client.post("/api/simulate", json={
            "n_bits": 10000,
            "seed": 42
        })
        assert response.status_code == 422
        assert "detail" in response.json()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
