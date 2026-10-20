"""
故障诊断API集成测试（阶段02）

测试新增API端点的功能和错误处理
"""

import pytest
from fastapi.testclient import TestClient
from main import app
import math

client = TestClient(app)


class TestFaultDiagnosisAPI:
    """故障诊断API测试类"""

    def test_fault_diagnosis_endpoint_exists(self):
        """测试: 故障诊断端点存在"""
        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 1000,
            "dc_offset": 0.5,
            "seed": 42
        })
        assert response.status_code == 200

    def test_fault_diagnosis_returns_complete_data(self):
        """测试: 故障诊断返回完整数据"""
        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 10000,
            "dc_offset": 0.8,
            "seed": 42
        })

        assert response.status_code == 200
        data = response.json()

        # 验证必需字段存在
        assert 'experiment_id' in data
        assert 'normal' in data
        assert 'with_fault' in data
        assert 'repaired' in data
        assert 'diagnosis' in data
        assert 'measurement' in data
        assert 'samples' in data

        # 验证正常状态
        assert 'ber' in data['normal']
        assert 'n_errors' in data['normal']
        assert 'threshold' in data['normal']

        # 验证诊断信息
        assert 'has_dc_offset' in data['diagnosis']
        assert 'estimated_offset' in data['diagnosis']
        assert 'message' in data['diagnosis']

    def test_fault_diagnosis_with_zero_offset(self):
        """测试: DC偏移为0时的行为"""
        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 10.0,
            "n_bits": 1000,
            "dc_offset": 0.0,
            "seed": 42
        })

        assert response.status_code == 200
        data = response.json()

        # 无偏移时，正常和故障状态应该相同
        assert abs(data['normal']['ber'] - data['with_fault']['ber']) < 1e-6

    def test_fault_diagnosis_rejects_nan(self):
        """测试: 拒绝NaN输入"""
        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": float('nan'),
            "n_bits": 1000,
            "dc_offset": 0.5
        })
        assert response.status_code == 422

        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 1000,
            "dc_offset": float('nan')
        })
        assert response.status_code == 422

    def test_fault_diagnosis_rejects_infinity(self):
        """测试: 拒绝Infinity输入"""
        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": float('inf'),
            "n_bits": 1000,
            "dc_offset": 0.5
        })
        assert response.status_code == 422

    def test_fault_diagnosis_validates_range(self):
        """测试: 参数范围验证"""
        # DC偏移超出范围
        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 1000,
            "dc_offset": 5.0  # 超过2.0限制
        })
        assert response.status_code == 422


class TestCustomThresholdAPI:
    """自定义门限API测试类"""

    def test_apply_threshold_endpoint_exists(self):
        """测试: 自定义门限端点存在"""
        # 先运行一个实验获取experiment_id
        diag_response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 1000,
            "dc_offset": 0.5,
            "seed": 42
        })
        experiment_id = diag_response.json()['experiment_id']

        # 应用自定义门限
        response = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.6
        })
        assert response.status_code == 200

    def test_apply_threshold_returns_result(self):
        """测试: 应用门限返回判决结果"""
        # 先运行实验
        diag_response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 5000,
            "dc_offset": 0.8,
            "seed": 42
        })
        experiment_id = diag_response.json()['experiment_id']

        # 应用门限
        response = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.8
        })

        assert response.status_code == 200
        data = response.json()

        assert 'ber' in data
        assert 'n_errors' in data
        assert 'threshold' in data
        assert data['threshold'] == 0.8

    def test_apply_threshold_with_invalid_experiment_id(self):
        """测试: 无效实验ID返回404"""
        response = client.post("/api/apply-threshold", json={
            "experiment_id": "nonexistent-id",
            "threshold": 0.5
        })
        assert response.status_code == 404

    def test_apply_threshold_rejects_nan(self):
        """测试: 拒绝NaN门限"""
        diag_response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 1000,
            "dc_offset": 0.5,
            "seed": 42
        })
        experiment_id = diag_response.json()['experiment_id']

        response = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": float('nan')
        })
        assert response.status_code == 422

    def test_different_thresholds_give_different_results(self):
        """测试: 不同门限产生不同结果"""
        # 运行实验
        diag_response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 5000,
            "dc_offset": 0.8,
            "seed": 42
        })
        experiment_id = diag_response.json()['experiment_id']

        # 应用两个不同门限
        response1 = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.0
        })
        response2 = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.8
        })

        data1 = response1.json()
        data2 = response2.json()

        # 不同门限应该产生不同的误码数
        assert data1['n_errors'] != data2['n_errors']


class TestBackwardCompatibility:
    """向后兼容性测试类"""

    def test_original_simulate_endpoint_still_works(self):
        """测试: 原有/api/simulate端点仍然工作"""
        response = client.post("/api/simulate", json={
            "eb_n0_db": 8.0,
            "n_bits": 1000,
            "seed": 42
        })

        assert response.status_code == 200
        data = response.json()

        # 验证阶段01的字段仍然存在
        assert 'eb_n0_db' in data
        assert 'n_bits' in data
        assert 'n_errors' in data
        assert 'ber_theoretical' in data
        assert 'ber_measured' in data
        assert 'rx_samples' in data
        assert 'tx_symbols_samples' in data


class TestCORSAndMiddleware:
    """CORS和中间件测试类"""

    def test_cors_headers_present(self):
        """测试: CORS头存在（P2修复：检查实际CORS头）"""
        # 对于允许的origin，应该返回Access-Control-Allow-Origin头
        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 1000,
            "dc_offset": 0.5,
            "seed": 42
        }, headers={"Origin": "http://localhost:5173"})

        assert response.status_code == 200
        # 验证CORS头存在
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

    def test_nonfinite_value_middleware_still_works(self):
        """测试: 非有限值中间件仍然工作"""
        # 这个测试验证阶段01的F03修复仍然有效
        response = client.post("/api/simulate", json={
            "eb_n0_db": float('inf'),
            "n_bits": 1000
        })
        assert response.status_code == 422


class TestRealWorldScenario:
    """真实场景测试类"""

    def test_complete_diagnosis_repair_workflow(self):
        """测试: 完整的诊断-修复工作流"""
        # 步骤1: 运行故障诊断实验
        diag_response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 10000,
            "dc_offset": 0.8,
            "seed": 42,
            "sample_size": 1000
        })

        assert diag_response.status_code == 200
        diag_data = diag_response.json()

        # 步骤2: 观察故障导致BER上升
        assert diag_data['with_fault']['ber'] > diag_data['normal']['ber']

        # 步骤3: 系统自动诊断并建议门限
        assert diag_data['diagnosis']['has_dc_offset']
        suggested_threshold = diag_data['diagnosis']['suggested_threshold']

        # 步骤4: 自动应用建议门限，修复应该改善BER
        assert diag_data['repaired']['ber'] < diag_data['with_fault']['ber']

        # 步骤5: 用户尝试手动调整门限
        experiment_id = diag_data['experiment_id']
        manual_response = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.7  # 手动尝试不同门限
        })

        assert manual_response.status_code == 200
        manual_data = manual_response.json()

        # 验证手动调整真正重新计算了BER
        assert 'ber' in manual_data
        assert 'n_errors' in manual_data

    def test_reproducibility_with_seed(self):
        """测试: 使用相同种子的可复现性"""
        params = {
            "eb_n0_db": 8.0,
            "n_bits": 5000,
            "dc_offset": 0.6,
            "seed": 12345
        }

        # 运行两次
        response1 = client.post("/api/fault-diagnosis", json=params)
        response2 = client.post("/api/fault-diagnosis", json=params)

        data1 = response1.json()
        data2 = response2.json()

        # 所有数值结果应该相同（除了experiment_id）
        assert data1['normal']['ber'] == data2['normal']['ber']
        assert data1['with_fault']['ber'] == data2['with_fault']['ber']
        assert data1['repaired']['ber'] == data2['repaired']['ber']
        assert data1['measurement']['rx_mean'] == data2['measurement']['rx_mean']


class TestPairedExperimentAPI:
    """E组：配对实验API测试（seed复用验证）"""

    def test_seed_fixed_threshold_consistency(self):
        """测试: seed=42时重复设置相同门限得到相同结果"""
        # 创建实验
        diag_response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 10000,
            "dc_offset": 0.8,
            "seed": 42
        })
        experiment_id = diag_response.json()['experiment_id']

        # 第一次应用门限T=0
        response1 = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.0
        })
        data1 = response1.json()

        # 第二次应用相同门限T=0
        response2 = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.0
        })
        data2 = response2.json()

        # 必须完全一致
        assert data1['ber'] == data2['ber']
        assert data1['n_errors'] == data2['n_errors']

    def test_seed_none_threshold_consistency(self):
        """测试: seed=None时重复设置相同门限得到相同结果"""
        # 创建实验（无种子）
        diag_response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 10000,
            "dc_offset": 0.8
        })
        experiment_id = diag_response.json()['experiment_id']

        # 第一次应用门限T=0
        response1 = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.0
        })
        data1 = response1.json()

        # 第二次应用相同门限T=0
        response2 = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.0
        })
        data2 = response2.json()

        # 必须严格一致（使用缓存的相同数据）
        assert data1['ber'] == data2['ber']
        assert data1['n_errors'] == data2['n_errors']

    def test_different_thresholds_same_samples(self):
        """测试: 改变门限后接收样本不改变"""
        diag_response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 10000,
            "dc_offset": 0.8,
            "seed": 42
        })
        experiment_id = diag_response.json()['experiment_id']
        initial_with_fault = diag_response.json()['with_fault']['n_errors']

        # 应用不同门限
        response1 = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.0
        })
        n_errors_t0 = response1.json()['n_errors']

        response2 = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.8
        })
        n_errors_t08 = response2.json()['n_errors']

        # 不同门限应该产生不同结果
        assert n_errors_t0 != n_errors_t08

        # 第一次T=0的结果应该等于初始诊断的with_fault（threshold=0）
        assert n_errors_t0 == initial_with_fault

    def test_seed_42_reference_values(self):
        """测试: seed=42的参考验证（Eb/N0=8dB, n=10000, dc=0.8）"""
        diag_response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 10000,
            "dc_offset": 0.8,
            "seed": 42
        })
        data = diag_response.json()
        experiment_id = data['experiment_id']

        # 验证正常状态：2误码（参考值）
        assert data['normal']['n_errors'] == 2

        # 验证故障T=0：1230误码（参考值）
        assert data['with_fault']['n_errors'] == 1230

        # 验证建议门限修复后接近正常（2误码）
        assert data['repaired']['n_errors'] == 2

        # 手动应用T=0.7
        response_t07 = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.7
        })
        # 验证T=0.7：3误码（参考值）
        assert response_t07.json()['n_errors'] == 3


class TestCacheManagement:
    """F组：缓存容量测试"""

    def test_cache_capacity_limit(self):
        """测试: 缓存严格限制在10个实验"""
        experiment_ids = []

        # 创建11个实验
        for i in range(11):
            response = client.post("/api/fault-diagnosis", json={
                "eb_n0_db": 8.0,
                "n_bits": 1000,
                "dc_offset": 0.5,
                "seed": i
            })
            experiment_ids.append(response.json()['experiment_id'])

        # 最旧的实验（第1个）应该被淘汰
        oldest_response = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_ids[0],
            "threshold": 0.5
        })
        assert oldest_response.status_code == 404

        # 最新的10个应该仍然有效
        for exp_id in experiment_ids[1:11]:
            response = client.post("/api/apply-threshold", json={
                "experiment_id": exp_id,
                "threshold": 0.5
            })
            assert response.status_code == 200


class TestRuntimeErrorHandling:
    """P2修复：RuntimeError异常处理测试"""

    def test_fault_diagnosis_runtime_error_returns_500(self, monkeypatch):
        """测试: 故障诊断内部RuntimeError返回500"""
        from bpsk_simulator import BPSKSimulator

        # Mock run_fault_diagnosis_experiment抛出RuntimeError
        def mock_run(*args, **kwargs):
            raise RuntimeError("simulated internal error")

        monkeypatch.setattr(BPSKSimulator, "run_fault_diagnosis_experiment", mock_run)

        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 1000,
            "dc_offset": 0.5,
            "seed": 42
        })

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "simulated internal error" in data["detail"]

    def test_apply_threshold_runtime_error_returns_500(self, monkeypatch):
        """测试: 应用门限内部RuntimeError返回500"""
        # 先创建一个有效实验
        diag_response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 8.0,
            "n_bits": 1000,
            "dc_offset": 0.5,
            "seed": 42
        })
        experiment_id = diag_response.json()['experiment_id']

        # Mock apply_custom_threshold抛出RuntimeError
        from bpsk_simulator import BPSKSimulator

        def mock_apply(*args, **kwargs):
            raise RuntimeError("simulated threshold error")

        monkeypatch.setattr(BPSKSimulator, "apply_custom_threshold", mock_apply)

        response = client.post("/api/apply-threshold", json={
            "experiment_id": experiment_id,
            "threshold": 0.5
        })

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "simulated threshold error" in data["detail"]


class TestInvalidUTF8:
    """P2修复：非法UTF-8请求处理测试"""

    def test_fault_diagnosis_invalid_utf8_returns_422(self):
        """测试: 故障诊断非法UTF-8返回422"""
        # 发送非法UTF-8字节
        response = client.post(
            "/api/fault-diagnosis",
            content=b'\xff',
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], list)
        assert len(data["detail"]) > 0
        assert "UTF-8" in data["detail"][0]["msg"] or "decode" in data["detail"][0]["msg"]

    def test_apply_threshold_invalid_utf8_returns_422(self):
        """测试: 应用门限非法UTF-8返回422"""
        response = client.post(
            "/api/apply-threshold",
            content=b'\xff\xfe',
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert "detail" in data

    def test_simulate_invalid_utf8_returns_422(self):
        """测试: 仿真非法UTF-8返回422"""
        response = client.post(
            "/api/simulate",
            content=b'\x80\x81\x82',
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert "detail" in data


class TestAUD3_07_SeedValidation:
    """AUD3-07: 非法seed必须返回422而非400"""

    def test_fault_diagnosis_negative_seed_returns_422(self):
        """AUD3-07: 故障诊断负seed返回422"""
        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 10.0,
            "n_bits": 100,
            "seed": -1
        })

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_simulate_negative_seed_returns_422(self):
        """AUD3-07: 仿真负seed返回422"""
        response = client.post("/api/simulate", json={
            "eb_n0_db": 10.0,
            "n_bits": 100,
            "seed": -1
        })

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_fault_diagnosis_accepts_zero_seed(self):
        """AUD3-07: seed=0是合法的非负整数"""
        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 10.0,
            "n_bits": 100,
            "seed": 0
        })

        assert response.status_code == 200

    def test_simulate_accepts_positive_seed(self):
        """AUD3-07: 正seed正常工作"""
        response = client.post("/api/simulate", json={
            "eb_n0_db": 10.0,
            "n_bits": 100,
            "seed": 42
        })

        assert response.status_code == 200

    def test_runtime_error_still_returns_500(self, monkeypatch):
        """AUD3-07: 真正的RuntimeError仍然返回500"""
        from bpsk_simulator import BPSKSimulator

        def mock_init(*args, **kwargs):
            raise RuntimeError("simulated internal error")

        monkeypatch.setattr(BPSKSimulator, "__init__", mock_init)

        response = client.post("/api/fault-diagnosis", json={
            "eb_n0_db": 10.0,
            "n_bits": 100,
            "seed": 42
        })

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "internal error" in data["detail"].lower()
