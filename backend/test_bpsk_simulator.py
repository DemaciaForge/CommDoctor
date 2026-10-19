"""
BPSK仿真器测试套件

验证BPSK调制、AWGN信道、解调和误码率计算的正确性
"""

import pytest
import numpy as np
from bpsk_simulator import BPSKSimulator


class TestBPSKSimulator:
    """BPSK仿真器测试类"""

    def test_modulation(self):
        """测试BPSK调制映射正确性"""
        sim = BPSKSimulator(seed=42)
        bits = np.array([0, 1, 0, 1, 1, 0])
        symbols = sim.modulate_bpsk(bits)
        expected = np.array([-1, 1, -1, 1, 1, -1])
        np.testing.assert_array_equal(symbols, expected)

    def test_demodulation_no_noise(self):
        """测试无噪声情况下解调正确性"""
        sim = BPSKSimulator(seed=42)
        n_bits = 1000
        tx_bits = sim.generate_bits(n_bits)
        tx_symbols = sim.modulate_bpsk(tx_bits)
        rx_bits = sim.demodulate_bpsk(tx_symbols)
        np.testing.assert_array_equal(tx_bits, rx_bits)

    def test_theoretical_ber_values(self):
        """测试理论BER计算与参考值一致"""
        sim = BPSKSimulator()

        # 参考值来自任务说明
        test_cases = [
            (0, 0.078649603525),
            (5, 0.005953867148),
            (10, 0.0000038721082),
        ]

        for eb_n0_db, expected_ber in test_cases:
            calculated_ber = sim.calculate_ber_theoretical(eb_n0_db)
            # 使用相对误差容限
            np.testing.assert_allclose(
                calculated_ber, expected_ber,
                rtol=1e-6,
                err_msg=f"Theoretical BER mismatch at {eb_n0_db}dB"
            )

    def test_awgn_noise_variance(self):
        """测试AWGN噪声方差符合理论模型"""
        sim = BPSKSimulator(seed=42)
        eb_n0_db = 10
        n_samples = 100000

        # 生成零均值符号并添加噪声
        symbols = np.zeros(n_samples)
        received = sim.add_awgn(symbols, eb_n0_db)

        # 噪声 = 接收信号 - 发送信号
        noise = received - symbols

        # 理论噪声方差
        eb_n0_linear = 10 ** (eb_n0_db / 10)
        expected_variance = 1 / (2 * eb_n0_linear)

        # 实测噪声方差
        measured_variance = np.var(noise)

        # 允许统计波动
        np.testing.assert_allclose(
            measured_variance, expected_variance,
            rtol=0.05,
            err_msg=f"Noise variance mismatch at {eb_n0_db}dB"
        )

    def test_reproducibility_with_seed(self):
        """测试固定随机种子时结果可复现"""
        seed = 123
        n_bits = 1000
        eb_n0_db = 8

        sim1 = BPSKSimulator(seed=seed)
        result1 = sim1.run_simulation(n_bits, eb_n0_db)

        sim2 = BPSKSimulator(seed=seed)
        result2 = sim2.run_simulation(n_bits, eb_n0_db)

        assert result1['n_errors'] == result2['n_errors']
        assert result1['ber_measured'] == result2['ber_measured']
        np.testing.assert_array_equal(result1['rx_samples'], result2['rx_samples'])

    def test_low_snr_ber(self):
        """测试低SNR下实测BER符合统计预期"""
        sim = BPSKSimulator(seed=42)
        n_bits = 10000
        eb_n0_db = 0  # 低SNR，理论BER约7.86%

        result = sim.run_simulation(n_bits, eb_n0_db)
        ber_theoretical = result['ber_theoretical']
        ber_measured = result['ber_measured']

        # 允许较大的统计误差范围（约20%相对误差）
        assert abs(ber_measured - ber_theoretical) / ber_theoretical < 0.2

    def test_high_snr_ber(self):
        """测试高SNR下实测BER允许为零"""
        sim = BPSKSimulator(seed=42)
        n_bits = 10000
        eb_n0_db = 15  # 高SNR，理论BER极小

        result = sim.run_simulation(n_bits, eb_n0_db)

        # 高SNR下，实测BER可能为0（样本量不足以观察到误码）
        assert result['ber_measured'] >= 0
        assert result['n_errors'] >= 0

        # 理论BER应该极小
        assert result['ber_theoretical'] < 1e-10

    def test_simulation_result_structure(self):
        """测试仿真结果数据结构正确"""
        sim = BPSKSimulator(seed=42)
        result = sim.run_simulation(n_bits=1000, eb_n0_db=8, sample_size=100)

        # 检查必需字段
        required_fields = [
            'eb_n0_db', 'n_bits', 'n_errors',
            'ber_theoretical', 'ber_measured',
            'seed', 'rx_samples', 'tx_symbols_samples'
        ]
        for field in required_fields:
            assert field in result

        # 检查数据类型
        assert isinstance(result['eb_n0_db'], (int, float))
        assert isinstance(result['n_bits'], int)
        assert isinstance(result['n_errors'], int)
        assert isinstance(result['ber_theoretical'], float)
        assert isinstance(result['ber_measured'], float)
        assert isinstance(result['rx_samples'], list)
        assert len(result['rx_samples']) == 100

    def test_error_input_validation(self):
        """测试错误输入能够妥善处理"""
        sim = BPSKSimulator()

        # 测试零比特数
        with pytest.raises((ValueError, ZeroDivisionError)):
            sim.run_simulation(n_bits=0, eb_n0_db=10)

    def test_medium_snr_ber(self):
        """测试中等SNR下实测BER与理论BER一致性"""
        sim = BPSKSimulator(seed=42)
        n_bits = 100000  # 增加样本量以减少统计误差
        eb_n0_db = 8

        result = sim.run_simulation(n_bits, eb_n0_db)
        ber_theoretical = result['ber_theoretical']
        ber_measured = result['ber_measured']

        # 8dB时理论BER约0.00019，允许30%相对误差
        relative_error = abs(ber_measured - ber_theoretical) / ber_theoretical
        assert relative_error < 0.3, \
            f"BER mismatch: theoretical={ber_theoretical}, measured={ber_measured}"

    def test_uint8_modulation_overflow(self):
        """测试F04: uint8类型调制不应溢出"""
        sim = BPSKSimulator(seed=42)

        # 测试uint8输入
        bits_uint8 = np.array([0, 1, 0, 1], dtype=np.uint8)
        symbols = sim.modulate_bpsk(bits_uint8)
        expected = np.array([-1, 1, -1, 1])
        np.testing.assert_array_equal(symbols, expected)

        # 测试bool输入
        bits_bool = np.array([False, True, False, True])
        symbols = sim.modulate_bpsk(bits_bool)
        np.testing.assert_array_equal(symbols, expected)

    def test_modulation_invalid_bits(self):
        """测试F04: 非0/1比特应该抛出错误"""
        sim = BPSKSimulator(seed=42)

        # 测试包含2的数组
        bits_invalid = np.array([0, 1, 2, 1])
        with pytest.raises(ValueError, match="only 0 or 1"):
            sim.modulate_bpsk(bits_invalid)

    def test_modulation_decimal_rejection(self):
        """测试F04最终修复: 所有float输入应被拒绝（包括0.0, 1.0）"""
        sim = BPSKSimulator(seed=42)

        # 测试包含小数的浮点数组
        bits_with_decimals = np.array([0.0, 1.0, 0.5, 1.5])
        with pytest.raises(ValueError, match="Float inputs not allowed"):
            sim.modulate_bpsk(bits_with_decimals)

        # 测试纯整数值的浮点数组也应被拒绝（F04要求）
        bits_float_int = np.array([0.0, 1.0, 0.0, 1.0])
        with pytest.raises(ValueError, match="Float inputs not allowed"):
            sim.modulate_bpsk(bits_float_int)

    def test_modulation_negative_rejection(self):
        """测试F04第三轮: 负数应被拒绝"""
        sim = BPSKSimulator(seed=42)

        bits_negative = np.array([0, 1, -1, 1])
        with pytest.raises(ValueError, match="only 0 or 1"):
            sim.modulate_bpsk(bits_negative)

    def test_modulation_large_integer_rejection(self):
        """测试F04第三轮: 超大整数应被拒绝"""
        sim = BPSKSimulator(seed=42)

        bits_large = np.array([0, 1, 1000, 1])
        with pytest.raises(ValueError, match="only 0 or 1"):
            sim.modulate_bpsk(bits_large)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
