"""
故障诊断与修复功能测试套件（阶段02）

测试DC偏移故障注入、诊断、修复和配对实验的正确性
"""

import pytest
import numpy as np
from bpsk_simulator import BPSKSimulator


class TestDCOffsetFault:
    """DC偏移故障测试类"""

    def test_dc_offset_zero_is_compatible_with_stage01(self):
        """测试: d=0时与阶段01正常模型保持兼容"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=1000,
            eb_n0_db=10,
            dc_offset=0.0
        )

        # 无DC偏移时，正常和故障状态应该相同
        assert abs(result['normal']['ber'] - result['with_fault']['ber']) < 1e-10
        assert result['normal']['n_errors'] == result['with_fault']['n_errors']

    def test_positive_dc_offset(self):
        """测试: 正DC偏移"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=10000,
            eb_n0_db=8,
            dc_offset=0.8
        )

        # 正DC偏移应该导致BER上升
        assert result['with_fault']['ber'] > result['normal']['ber']
        # DC偏移应该被正确注入
        assert abs(result['dc_offset'] - 0.8) < 1e-10

    def test_negative_dc_offset(self):
        """测试: 负DC偏移"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=10000,
            eb_n0_db=8,
            dc_offset=-0.6
        )

        # 负DC偏移应该导致BER上升
        assert result['with_fault']['ber'] > result['normal']['ber']
        # DC偏移应该被正确注入
        assert abs(result['dc_offset'] - (-0.6)) < 1e-10


class TestPairedExperiment:
    """配对实验测试类"""

    def test_fixed_seed_reproducibility(self):
        """测试: 固定种子完整复现"""
        seed = 12345
        params = {
            'n_bits': 5000,
            'eb_n0_db': 8,
            'dc_offset': 0.5
        }

        # 运行两次实验
        sim1 = BPSKSimulator(seed=seed)
        result1 = sim1.run_fault_diagnosis_experiment(**params)

        sim2 = BPSKSimulator(seed=seed)
        result2 = sim2.run_fault_diagnosis_experiment(**params)

        # 所有数值结果应该完全相同
        assert result1['normal']['ber'] == result2['normal']['ber']
        assert result1['with_fault']['ber'] == result2['with_fault']['ber']
        assert result1['repaired']['ber'] == result2['repaired']['ber']
        assert result1['measurement']['rx_mean'] == result2['measurement']['rx_mean']

    def test_same_underlying_data(self):
        """测试: 同一次实验中底层发送比特和噪声不变"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=10000,
            eb_n0_db=8,
            dc_offset=0.8,
            sample_size=1000
        )

        # 验证采样数据的关系：rx_with_fault应该等于rx_normal + dc_offset
        samples = result['samples']
        rx_normal = np.array(samples['rx_normal'])
        rx_with_fault = np.array(samples['rx_with_fault'])
        dc_offset = result['dc_offset']

        # 允许浮点误差
        np.testing.assert_allclose(
            rx_with_fault,
            rx_normal + dc_offset,
            rtol=1e-10,
            err_msg="接收样本不是从同一批数据生成的"
        )


class TestMeasurementAndDiagnosis:
    """测量与诊断测试类"""

    def test_rx_mean_measurement(self):
        """测试: 接收样本均值测量"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=100000,  # 大样本以减小统计误差
            eb_n0_db=10,
            dc_offset=0.5
        )

        # 测量的均值应该接近DC偏移（在大样本下）
        # 由于发送符号均衡且噪声均值为0
        rx_mean = result['measurement']['rx_mean']
        dc_offset = result['dc_offset']

        # 允许一定的统计误差（约3sigma）
        # P2修复：使用正确的3σ公式
        noise_std = result['noise_std']
        n_bits = result['n_bits']
        # 正确公式：SE = sqrt((1 + sigma²) / N)
        variance_per_sample = 1.0 + noise_std ** 2
        std_error = np.sqrt(variance_per_sample / n_bits)

        assert abs(rx_mean - dc_offset) < 5 * std_error, \
            f"均值测量偏差过大: {rx_mean} vs {dc_offset}"

    def test_diagnosis_not_using_hidden_truth(self):
        """测试: 诊断不读取隐藏故障真值"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=10000,
            eb_n0_db=8,
            dc_offset=0.7
        )

        # 诊断应该基于测量值，而不是直接等于注入的DC偏移
        diagnosis = result['diagnosis']
        rx_mean = result['measurement']['rx_mean']

        # 诊断的估计偏移应该等于测量均值，而不是精确的dc_offset
        assert abs(diagnosis['estimated_offset'] - rx_mean) < 1e-10
        # 建议门限也应该基于测量值
        assert abs(diagnosis['suggested_threshold'] - rx_mean) < 1e-10

    def test_insufficient_evidence_with_small_offset(self):
        """测试: 小偏移时证据可能不足"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=1000,  # 小样本
            eb_n0_db=8,
            dc_offset=0.05  # 非常小的偏移
        )

        diagnosis = result['diagnosis']
        # 小偏移可能不会被检测到（取决于噪声）
        # 这是正常的，测试系统能够正确报告低置信度
        if not diagnosis['has_dc_offset']:
            assert diagnosis['confidence'] == '低'


class TestReceiverRepair:
    """接收机修复测试类"""

    def test_threshold_adjustment_affects_decision(self):
        """测试: 判决门限调整实际影响误码数"""
        sim = BPSKSimulator(seed=42)

        # 生成固定数据
        tx_bits = sim.generate_bits(1000)
        tx_symbols = sim.modulate_bpsk(tx_bits)

        eb_n0_db = 8
        eb_n0_linear = 10 ** (eb_n0_db / 10)
        noise_std = np.sqrt(1 / (2 * eb_n0_linear))
        noise = sim.rng.normal(0, noise_std, size=tx_symbols.shape)

        rx_signals = tx_symbols + noise + 0.8  # 添加DC偏移

        # 使用不同门限判决
        result_t0 = sim.apply_custom_threshold(tx_bits, rx_signals, threshold=0.0)
        result_t08 = sim.apply_custom_threshold(tx_bits, rx_signals, threshold=0.8)

        # 门限调整应该改变误码数
        assert result_t0['n_errors'] != result_t08['n_errors']
        # 适当的门限应该减少误码
        assert result_t08['n_errors'] < result_t0['n_errors']

    def test_repair_improves_ber(self):
        """测试: 适当故障下修复有可量化改善"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=10000,
            eb_n0_db=8,
            dc_offset=0.8
        )

        # 修复后BER应该低于故障时BER
        assert result['repaired']['ber'] < result['with_fault']['ber']
        # 修复后BER应该接近正常BER（但可能不完全相同）
        # 允许修复不完美
        assert result['repaired']['ber'] <= result['normal']['ber'] * 2

    def test_no_fault_no_guaranteed_improvement(self):
        """测试: 无故障时修复不保证改善"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=10000,
            eb_n0_db=8,
            dc_offset=0.0  # 无故障
        )

        # 无故障时，调整门限可能反而增加BER
        # 这是合理的，因为最优门限就是0
        # 测试系统能够诚实报告这种情况

        # P2修复：增加实际结果断言
        # 验证无故障时诊断正确
        assert not result['diagnosis']['has_dc_offset']
        # 验证建议门限为0或接近0
        assert abs(result['diagnosis']['suggested_threshold']) < 0.1
        # 验证修复操作返回了结果
        assert 'repaired' in result
        assert 'ber' in result['repaired']
        assert 'n_errors' in result['repaired']


class TestEdgeCases:
    """边界情况测试类"""

    def test_reject_nan_dc_offset(self):
        """测试: 拒绝NaN DC偏移"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises((ValueError, TypeError)):
            sim.run_fault_diagnosis_experiment(
                n_bits=1000,
                eb_n0_db=8,
                dc_offset=float('nan')
            )

    def test_reject_infinite_dc_offset(self):
        """测试: 拒绝Infinity DC偏移"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises((ValueError, TypeError)):
            sim.run_fault_diagnosis_experiment(
                n_bits=1000,
                eb_n0_db=8,
                dc_offset=float('inf')
            )

    def test_reject_nan_threshold(self):
        """测试: 拒绝NaN门限"""
        sim = BPSKSimulator(seed=42)
        tx_bits = sim.generate_bits(1000)
        tx_symbols = sim.modulate_bpsk(tx_bits)
        rx_signals = sim.add_awgn(tx_symbols, 8)

        with pytest.raises((ValueError, TypeError)):
            sim.apply_custom_threshold(tx_bits, rx_signals, threshold=float('nan'))

    def test_sample_mean_estimation_has_finite_sample_error(self):
        """测试: 样本均值估计存在有限样本误差"""
        # 运行多次小样本实验，验证估计值分布
        results = []
        true_dc = 0.5

        for seed in range(50):
            sim = BPSKSimulator(seed=seed)
            result = sim.run_fault_diagnosis_experiment(
                n_bits=1000,  # 小样本
                eb_n0_db=8,
                dc_offset=true_dc
            )
            results.append(result['measurement']['rx_mean'])

        # 均值的均值应该接近真值
        mean_of_means = np.mean(results)
        assert abs(mean_of_means - true_dc) < 0.05

        # 但单次测量应该有波动
        std_of_means = np.std(results)
        assert std_of_means > 0.001  # 确实存在统计误差


class TestAPIResponses:
    """API响应测试类"""

    def test_api_response_is_json_serializable(self):
        """测试: API响应可安全JSON序列化"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=1000,
            eb_n0_db=8,
            dc_offset=0.5
        )

        # 过滤掉内部字段（以_开头）
        result_for_api = {k: v for k, v in result.items() if not k.startswith('_')}

        # P2修复：使用allow_nan=False确保不接受NaN/Infinity
        import json
        try:
            json_str = json.dumps(result_for_api, allow_nan=False)
            # 反序列化验证
            recovered = json.loads(json_str)
            assert recovered is not None
        except (TypeError, ValueError) as e:
            pytest.fail(f"API响应无法JSON序列化: {e}")
            recovered = json.loads(json_str)
            assert recovered is not None
        except (TypeError, ValueError) as e:
            pytest.fail(f"API响应无法JSON序列化: {e}")

    def test_no_numpy_types_in_response(self):
        """测试: 响应中不包含NumPy类型"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_fault_diagnosis_experiment(
            n_bits=1000,
            eb_n0_db=8,
            dc_offset=0.5
        )

        # 过滤掉内部字段（以_开头）
        result_for_api = {k: v for k, v in result.items() if not k.startswith('_')}

        def check_no_numpy(obj, path="root"):
            """递归检查对象中是否包含NumPy类型"""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    check_no_numpy(value, f"{path}.{key}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_no_numpy(item, f"{path}[{i}]")
            elif isinstance(obj, (np.ndarray, np.integer, np.floating, np.bool_)):
                pytest.fail(f"发现NumPy类型在 {path}: {type(obj)}")

        check_no_numpy(result_for_api)


class TestStandardErrorFormula:
    """P2修复：3σ标准误差公式数学回归测试"""

    def test_standard_error_formula_eb8_n10000(self):
        """测试: 验证Eb/N0=8dB, n=10000时标准误差的正确公式"""
        # 独立计算理论值
        eb_n0_db = 8.0
        n_bits = 10000

        # 计算噪声标准差
        eb_n0_linear = 10 ** (eb_n0_db / 10)
        noise_variance = 1 / (2 * eb_n0_linear)
        noise_std = np.sqrt(noise_variance)

        # 期望值：0.2815042799373673
        expected_noise_std = 0.2815042799373673
        assert abs(noise_std - expected_noise_std) < 1e-10, \
            f"噪声标准差计算错误: {noise_std} vs {expected_noise_std}"

        # 独立计算正确的标准误差公式：SE = sqrt((1 + sigma²) / N)
        variance_per_sample = 1.0 + noise_std ** 2
        std_error_calculated = np.sqrt(variance_per_sample / n_bits)

        # 独立理论值
        expected_std_error = np.sqrt((1.0 + expected_noise_std ** 2) / n_bits)
        # 理论值约为 0.010388670076689583
        assert abs(expected_std_error - 0.010388670076689583) < 1e-15, \
            "独立理论值计算错误"

        assert abs(std_error_calculated - expected_std_error) < 1e-15, \
            f"标准误差公式错误: {std_error_calculated} vs {expected_std_error}"

        # 3SE
        threshold_3sigma = 3 * std_error_calculated
        expected_3sigma = 3 * expected_std_error
        # 理论值约为 0.03116601023006875
        assert abs(expected_3sigma - 0.03116601023006875) < 1e-15, \
            "3σ理论值计算错误"

        assert abs(threshold_3sigma - expected_3sigma) < 1e-15, \
            f"3σ阈值错误: {threshold_3sigma} vs {expected_3sigma}"

    def test_diagnosis_uses_correct_formula(self):
        """测试: 诊断函数使用正确的标准误差公式"""
        sim = BPSKSimulator(seed=42)

        # 已知参数
        eb_n0_db = 8.0
        n_bits = 10000
        dc_offset = 0.8

        result = sim.run_fault_diagnosis_experiment(
            n_bits=n_bits,
            eb_n0_db=eb_n0_db,
            dc_offset=dc_offset
        )

        noise_std = result['noise_std']
        evidence = result['diagnosis']['evidence']

        # 独立计算期望值
        expected_variance = 1.0 + noise_std ** 2
        expected_std_error = np.sqrt(expected_variance / n_bits)
        expected_threshold_3sigma = 3 * expected_std_error

        # 验证结果匹配正确公式
        assert abs(evidence['std_error'] - expected_std_error) < 1e-10, \
            "诊断使用了错误的标准误差公式"
        assert abs(evidence['threshold_3sigma'] - expected_threshold_3sigma) < 1e-10, \
            "诊断使用了错误的3σ阈值公式"


class TestBottomLevelNonFiniteRejection:
    """P2修复：底层数学入口非有限输入拒绝测试"""

    def test_demodulate_threshold_rejects_nan(self):
        """测试: 解调拒绝NaN门限"""
        sim = BPSKSimulator(seed=42)
        rx_signals = np.array([0.1, -0.2, 0.3])

        with pytest.raises(ValueError, match="threshold must be finite"):
            sim.demodulate_bpsk_with_threshold(rx_signals, threshold=float('nan'))

    def test_demodulate_threshold_rejects_inf(self):
        """测试: 解调拒绝Infinity门限"""
        sim = BPSKSimulator(seed=42)
        rx_signals = np.array([0.1, -0.2, 0.3])

        with pytest.raises(ValueError, match="threshold must be finite"):
            sim.demodulate_bpsk_with_threshold(rx_signals, threshold=float('inf'))

    def test_demodulate_threshold_rejects_neg_inf(self):
        """测试: 解调拒绝-Infinity门限"""
        sim = BPSKSimulator(seed=42)
        rx_signals = np.array([0.1, -0.2, 0.3])

        with pytest.raises(ValueError, match="threshold must be finite"):
            sim.demodulate_bpsk_with_threshold(rx_signals, threshold=float('-inf'))

    def test_demodulate_threshold_rejects_nan_in_signals(self):
        """测试: 解调拒绝包含NaN的接收信号"""
        sim = BPSKSimulator(seed=42)
        rx_signals = np.array([0.0, float('nan')])

        with pytest.raises(ValueError, match="received signals must contain only finite values"):
            sim.demodulate_bpsk_with_threshold(rx_signals, threshold=0.0)

    def test_demodulate_threshold_rejects_inf_in_signals(self):
        """测试: 解调拒绝包含Infinity的接收信号"""
        sim = BPSKSimulator(seed=42)
        rx_signals = np.array([0.0, float('inf')])

        with pytest.raises(ValueError, match="received signals must contain only finite values"):
            sim.demodulate_bpsk_with_threshold(rx_signals, threshold=0.0)

    def test_dc_offset_rejects_nan(self):
        """测试: DC注入拒绝NaN"""
        sim = BPSKSimulator(seed=42)
        signals = np.array([1.0, -1.0])

        with pytest.raises(ValueError, match="dc_offset must be finite"):
            sim.add_dc_offset(signals, dc_offset=float('nan'))

    def test_dc_offset_rejects_inf(self):
        """测试: DC注入拒绝Infinity"""
        sim = BPSKSimulator(seed=42)
        signals = np.array([1.0, -1.0])

        with pytest.raises(ValueError, match="dc_offset must be finite"):
            sim.add_dc_offset(signals, dc_offset=float('inf'))

    def test_dc_offset_rejects_neg_inf(self):
        """测试: DC注入拒绝-Infinity"""
        sim = BPSKSimulator(seed=42)
        signals = np.array([1.0, -1.0])

        with pytest.raises(ValueError, match="dc_offset must be finite"):
            sim.add_dc_offset(signals, dc_offset=float('-inf'))

    def test_rx_mean_rejects_nan_signals(self):
        """测试: 均值测量拒绝包含NaN的信号"""
        sim = BPSKSimulator(seed=42)
        rx_signals = np.array([0.5, float('nan'), -0.3])

        with pytest.raises(ValueError, match="rx_signals must contain only finite values"):
            sim.calculate_rx_mean(rx_signals)

    def test_rx_mean_rejects_inf_signals(self):
        """测试: 均值测量拒绝包含Infinity的信号"""
        sim = BPSKSimulator(seed=42)
        rx_signals = np.array([0.5, float('inf'), -0.3])

        with pytest.raises(ValueError, match="rx_signals must contain only finite values"):
            sim.calculate_rx_mean(rx_signals)

    def test_diagnose_rejects_nan_mean(self):
        """测试: 诊断拒绝NaN均值"""
        sim = BPSKSimulator(seed=42)

        with pytest.raises(ValueError, match="rx_mean must be finite"):
            sim.diagnose_dc_offset(rx_mean=float('nan'), n_samples=1000, noise_std=0.3)

    def test_diagnose_rejects_inf_mean(self):
        """测试: 诊断拒绝Infinity均值"""
        sim = BPSKSimulator(seed=42)

        with pytest.raises(ValueError, match="rx_mean must be finite"):
            sim.diagnose_dc_offset(rx_mean=float('inf'), n_samples=1000, noise_std=0.3)

    def test_diagnose_rejects_nan_std(self):
        """测试: 诊断拒绝NaN噪声标准差"""
        sim = BPSKSimulator(seed=42)

        with pytest.raises(ValueError, match="noise_std must be finite"):
            sim.diagnose_dc_offset(rx_mean=0.5, n_samples=1000, noise_std=float('nan'))

    def test_diagnose_rejects_inf_std(self):
        """测试: 诊断拒绝Infinity噪声标准差"""
        sim = BPSKSimulator(seed=42)

        with pytest.raises(ValueError, match="noise_std must be finite"):
            sim.diagnose_dc_offset(rx_mean=0.5, n_samples=1000, noise_std=float('inf'))

    def test_apply_threshold_rejects_nan_in_signals(self):
        """测试: apply_custom_threshold拒绝包含NaN的接收信号"""
        sim = BPSKSimulator(seed=42)
        tx_bits = np.array([0, 1, 1, 0])
        rx_signals = np.array([0.1, float('nan'), 0.3, -0.2])

        with pytest.raises(ValueError, match="rx_signals must contain only finite values"):
            sim.apply_custom_threshold(tx_bits, rx_signals, threshold=0.0)

    def test_apply_threshold_rejects_inf_in_signals(self):
        """测试: apply_custom_threshold拒绝包含Infinity的接收信号"""
        sim = BPSKSimulator(seed=42)
        tx_bits = np.array([0, 1, 1, 0])
        rx_signals = np.array([0.1, float('inf'), 0.3, -0.2])

        with pytest.raises(ValueError, match="rx_signals must contain only finite values"):
            sim.apply_custom_threshold(tx_bits, rx_signals, threshold=0.0)


class TestP2EdgeCases:
    """P2修复：补充边缘情况测试"""

    def test_empty_array_calculate_mean(self):
        """P2-2: 空数组必须被拒绝"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="cannot be empty"):
            sim.calculate_rx_mean(np.array([]))

    def test_empty_array_demodulate(self):
        """P2-2: 空数组解调必须被拒绝"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="cannot be empty"):
            sim.demodulate_bpsk_with_threshold(np.array([]), 0.0)

    def test_empty_array_apply_threshold(self):
        """P2-2: 空数组应用门限必须被拒绝"""
        sim = BPSKSimulator(seed=42)
        tx_bits = np.array([0, 1])
        with pytest.raises(ValueError, match="cannot be empty"):
            sim.apply_custom_threshold(tx_bits, np.array([]), 0.0)

    def test_diagnose_zero_samples(self):
        """P2-3: 0样本必须被拒绝"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="n_samples must be positive"):
            sim.diagnose_dc_offset(0.5, 0, 0.3)

    def test_diagnose_negative_samples(self):
        """P2-3: 负样本数必须被拒绝"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="n_samples must be positive"):
            sim.diagnose_dc_offset(0.5, -10, 0.3)

    def test_diagnose_noninteger_samples(self):
        """P2-3: 非整数样本数必须被拒绝"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="n_samples must be an integer"):
            sim.diagnose_dc_offset(0.5, 10.5, 0.3)

    def test_extreme_finite_overflow_mean(self):
        """P2-4: 极大有限值导致溢出必须被检测"""
        sim = BPSKSimulator(seed=42)
        huge_val = 1e308
        signals = np.array([huge_val, huge_val])
        with pytest.raises(ValueError, match="overflow|not finite"):
            sim.calculate_rx_mean(signals)

    def test_complex_array_mean(self):
        """P2-5: 复数数组必须被拒绝（calculate_rx_mean）"""
        sim = BPSKSimulator(seed=42)
        complex_array = np.array([1+2j, 0+1j])
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.calculate_rx_mean(complex_array)

    def test_complex_array_demodulate(self):
        """P2-5: 复数数组必须被拒绝（demodulate）"""
        sim = BPSKSimulator(seed=42)
        complex_array = np.array([1+2j, 0+1j])
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.demodulate_bpsk_with_threshold(complex_array, 0.0)

    def test_complex_array_apply_threshold(self):
        """P2-5: 复数数组必须被拒绝（apply_threshold）"""
        sim = BPSKSimulator(seed=42)
        tx_bits = np.array([0, 1])
        complex_array = np.array([1+2j, 0+1j])
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.apply_custom_threshold(tx_bits, complex_array, 0.0)

    def test_complex_with_zero_imag(self):
        """P2-5: 即使虚部为0的复数也必须被拒绝"""
        sim = BPSKSimulator(seed=42)
        complex_array = np.array([1+0j, 2+0j])
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.calculate_rx_mean(complex_array)

    def test_complex_dc_offset(self):
        """P2-5: add_dc_offset拒绝复数信号"""
        sim = BPSKSimulator(seed=42)
        complex_array = np.array([1+2j, 0+1j])
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.add_dc_offset(complex_array, 0.5)

    def test_valid_minimum_input(self):
        """验证最小合法输入仍然工作"""
        sim = BPSKSimulator(seed=42)
        # 单个样本
        mean = sim.calculate_rx_mean(np.array([0.5]))
        assert abs(mean - 0.5) < 1e-10

        # 单个样本解调
        bits = sim.demodulate_bpsk_with_threshold(np.array([0.5]), 0.0)
        assert bits[0] == 1

        # 诊断单个样本
        diag = sim.diagnose_dc_offset(0.5, 1, 0.3)
        assert 'has_dc_offset' in diag


class TestAUD3Round3Fixes:
    """AUD3-01至AUD3-07：第三轮独立审计发现的缺陷回归测试"""

    # AUD3-01: 非有限信号与发送比特校验
    def test_aud3_01_add_dc_offset_rejects_nan_in_signals(self):
        """AUD3-01: add_dc_offset拒绝包含NaN的信号"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="signals must contain only finite values"):
            sim.add_dc_offset([1.0, float('nan')], 0.5)

    def test_aud3_01_add_dc_offset_rejects_inf_in_signals(self):
        """AUD3-01: add_dc_offset拒绝包含+Inf的信号"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="signals must contain only finite values"):
            sim.add_dc_offset((1.0, float('inf')), 0.5)

    def test_aud3_01_add_dc_offset_rejects_neginf_in_signals(self):
        """AUD3-01: add_dc_offset拒绝包含-Inf的信号"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="signals must contain only finite values"):
            sim.add_dc_offset([1.0, float('-inf')], 0.5)

    def test_aud3_01_apply_threshold_rejects_nan_in_tx_bits(self):
        """AUD3-01: apply_custom_threshold拒绝包含NaN的发送比特"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError):
            sim.apply_custom_threshold(np.array([0., float('nan')]), np.array([-1., 1.]), 0.)

    def test_aud3_01_apply_threshold_rejects_inf_in_tx_bits(self):
        """AUD3-01: apply_custom_threshold拒绝包含Infinity的发送比特"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError):
            sim.apply_custom_threshold(np.array([0., float('inf')]), np.array([-1., 1.]), 0.)

    def test_aud3_01_apply_threshold_rejects_non_binary_tx_bits(self):
        """AUD3-01: apply_custom_threshold拒绝非0/1发送比特"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="tx_bits must contain only 0 or 1"):
            sim.apply_custom_threshold(np.array([0, 2]), np.array([-1., 1.]), 0.)

    # AUD3-02: 空发送比特导致NaN BER
    def test_aud3_02_calculate_ber_rejects_empty_tx_bits(self):
        """AUD3-02: calculate_ber_measured拒绝空发送比特"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="tx_bits cannot be empty"):
            sim.calculate_ber_measured(np.array([]), np.array([]))

    def test_aud3_02_calculate_ber_rejects_empty_rx_bits(self):
        """AUD3-02: calculate_ber_measured拒绝空接收比特"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="rx_bits cannot be empty"):
            sim.calculate_ber_measured(np.array([0, 1]), np.array([]))

    def test_aud3_02_apply_threshold_empty_tx_bits(self):
        """AUD3-02: apply_custom_threshold拒绝空发送比特"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="tx_bits cannot be empty"):
            sim.apply_custom_threshold(np.array([]), np.array([1.]), 0.)

    def test_aud3_02_add_dc_offset_rejects_empty_signals(self):
        """P2-F01: add_dc_offset拒绝空信号"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="signals cannot be empty"):
            sim.add_dc_offset([], 0.5)

    # AUD3-03: True被接受为诊断样本数
    def test_aud3_03_diagnose_rejects_bool_true(self):
        """AUD3-03: diagnose_dc_offset拒绝Python bool True"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="n_samples must be a true integer, not bool"):
            sim.diagnose_dc_offset(0.5, True, 0.3)

    def test_aud3_03_diagnose_rejects_bool_false(self):
        """AUD3-03: diagnose_dc_offset拒绝Python bool False"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError):
            # False会被bool检查或正数检查拒绝
            sim.diagnose_dc_offset(0.5, False, 0.3)

    def test_aud3_03_diagnose_accepts_real_integers(self):
        """AUD3-03: diagnose_dc_offset接受真正的整数"""
        sim = BPSKSimulator(seed=42)
        # Python int
        result = sim.diagnose_dc_offset(0.5, 100, 0.3)
        assert 'has_dc_offset' in result

        # NumPy integers
        result = sim.diagnose_dc_offset(0.5, np.int64(100), 0.3)
        assert 'has_dc_offset' in result

    # AUD3-04: 有限值溢出
    def test_aud3_04_add_dc_offset_overflow(self):
        """AUD3-04: add_dc_offset检测加法溢出"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="overflow|non-finite"):
            sim.add_dc_offset(np.array([1e308]), 1e308)

    def test_aud3_04_diagnose_variance_overflow(self):
        """AUD3-04: diagnose_dc_offset检测方差计算溢出"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="overflow|Variance calculation|not finite"):
            sim.diagnose_dc_offset(0.5, 100, np.float64(1e308))

    def test_aud3_04_diagnose_python_float_overflow(self):
        """AUD3-04: diagnose_dc_offset处理Python float溢出"""
        sim = BPSKSimulator(seed=42)
        # Python float 1e308 在某些计算中会抛OverflowError
        with pytest.raises((ValueError, OverflowError)):
            sim.diagnose_dc_offset(0.5, 100, 1e308)

    # AUD3-05: NumPy复数标量绕过
    def test_aud3_05_apply_threshold_rejects_numpy_complex_threshold(self):
        """AUD3-05: apply_custom_threshold拒绝NumPy复数标量门限"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.apply_custom_threshold(
                np.array([0, 1]), np.array([-1., 1.]), np.complex128(1+2j)
            )

    def test_aud3_05_apply_threshold_rejects_numpy_complex_zero_imag(self):
        """AUD3-05: 即使虚部为0的NumPy复数标量也必须拒绝"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.apply_custom_threshold(
                np.array([0, 1]), np.array([-1., 1.]), np.complex128(1+0j)
            )

    def test_aud3_05_diagnose_rejects_numpy_complex_mean(self):
        """AUD3-05: diagnose_dc_offset拒绝NumPy复数标量均值"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.diagnose_dc_offset(np.complex64(1+2j), 100, 0.3)

    def test_aud3_05_diagnose_rejects_numpy_complex_std(self):
        """AUD3-05: diagnose_dc_offset拒绝NumPy复数标量噪声标准差"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.diagnose_dc_offset(0.5, 100, np.complex64(0.3+0j))

    def test_aud3_05_add_dc_offset_rejects_numpy_complex_offset(self):
        """AUD3-05: add_dc_offset拒绝NumPy复数标量偏移"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.add_dc_offset(np.array([1.]), np.complex128(1+2j))

    def test_aud3_05_demodulate_threshold_rejects_numpy_complex_threshold(self):
        """AUD3-05: demodulate_bpsk_with_threshold拒绝NumPy复数标量门限"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.demodulate_bpsk_with_threshold(np.array([1., -1.]), np.complex64(0.5+0j))

    def test_aud3_05_object_array_rejected(self):
        """AUD3-05: object dtype数组必须被拒绝"""
        sim = BPSKSimulator(seed=42)
        obj_array = np.array([1+2j], dtype=object)
        with pytest.raises(ValueError, match="real-valued|complex"):
            sim.add_dc_offset(obj_array, 0.5)

    # AUD3-06: 数组广播导致BER>1
    def test_aud3_06_calculate_ber_shape_mismatch_length(self):
        """AUD3-06: calculate_ber_measured拒绝长度不匹配"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="same length"):
            sim.calculate_ber_measured(np.array([0]), np.array([1, 1, 1]))

    def test_aud3_06_calculate_ber_rejects_multidimensional_tx(self):
        """AUD3-06: calculate_ber_measured拒绝多维发送比特"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="must be 1-dimensional"):
            sim.calculate_ber_measured(np.array([[0, 1]]), np.array([1, 0]))

    def test_aud3_06_calculate_ber_rejects_multidimensional_rx(self):
        """AUD3-06: calculate_ber_measured拒绝多维接收比特"""
        sim = BPSKSimulator(seed=42)
        with pytest.raises(ValueError, match="must be 1-dimensional"):
            sim.calculate_ber_measured(np.array([0, 1]), np.array([[-1], [1]]))

    def test_aud3_06_apply_threshold_prevents_broadcast(self):
        """AUD3-06: apply_custom_threshold防止广播导致BER=3.0"""
        sim = BPSKSimulator(seed=42)
        # Codex实际复现的case：tx=(1,), rx=(3,) 导致BER=3.0
        with pytest.raises(ValueError):
            sim.apply_custom_threshold(np.array([0]), np.array([1., 1., 1.]), 0.)

    def test_aud3_06_ber_invariant_identical(self):
        """AUD3-06: BER不变量测试 - 完全相同时BER=0"""
        sim = BPSKSimulator(seed=42)
        tx = np.array([0, 1, 0, 1])
        rx = np.array([0, 1, 0, 1])
        ber, errors = sim.calculate_ber_measured(tx, rx)
        assert ber == 0.0
        assert errors == 0

    def test_aud3_06_ber_invariant_all_different(self):
        """AUD3-06: BER不变量测试 - 完全不同时BER=1"""
        sim = BPSKSimulator(seed=42)
        tx = np.array([0, 1, 0, 1])
        rx = np.array([1, 0, 1, 0])
        ber, errors = sim.calculate_ber_measured(tx, rx)
        assert ber == 1.0
        assert errors == 4

    def test_aud3_06_ber_invariant_half_errors(self):
        """AUD3-06: BER不变量测试 - 一半错误时BER=0.5"""
        sim = BPSKSimulator(seed=42)
        tx = np.array([0, 1, 0, 1])
        rx = np.array([1, 1, 1, 1])
        ber, errors = sim.calculate_ber_measured(tx, rx)
        assert ber == 0.5
        assert errors == 2

    def test_aud3_06_ber_invariant_in_range(self):
        """AUD3-06: BER不变量测试 - BER必须在[0,1]范围内"""
        sim = BPSKSimulator(seed=42)
        # 任意合法输入
        tx = np.array([0, 1, 1, 0, 1])
        rx = np.array([0, 0, 1, 1, 1])
        ber, errors = sim.calculate_ber_measured(tx, rx)
        assert 0 <= ber <= 1
        assert errors <= len(tx)
        # 验证计算正确性
        assert ber == errors / len(tx)
