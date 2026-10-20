"""
B07 和 B09 缺陷复现脚本
根据独立审计报告 STAGE02_P2_ROUND4_FINAL_AUDIT.md
"""
import numpy as np
from bpsk_simulator import BPSKSimulator

def test_b07_failures():
    """重放 B07 仍然失败的输入"""
    print("\n=== B07 缺陷复现 ===\n")

    # B07-1: apply_custom_threshold with object dtype tx
    print("B07-1: apply_custom_threshold with object dtype array")
    try:
        S = BPSKSimulator(42)
        result = S.apply_custom_threshold(
            np.array([0j, 1+0j], dtype=object),
            np.array([-1., 1.]),
            0.
        )
        print(f"  [FAIL] Should raise ValueError, but returned: {result}")
    except TypeError as e:
        print(f"  [FAIL] Leaked TypeError: {e}")
    except ValueError as e:
        print(f"  [PASS] Correctly raised ValueError: {e}")
    except Exception as e:
        print(f"  [FAIL] Unexpected {type(e).__name__}: {e}")

    # B07-2: demodulate_bpsk_with_threshold with超大整数
    print("\nB07-2: demodulate_bpsk_with_threshold with 10**400 threshold")
    try:
        S = BPSKSimulator(42)
        result = S.demodulate_bpsk_with_threshold(np.ones(2), 10**400)
        print(f"  [FAIL]: 应该抛出 ValueError，但返回了结果")
    except TypeError as e:
        print(f"  [FAIL]: 泄漏了 TypeError: {e}")
    except ValueError as e:
        print(f"  [PASS]: 正确抛出 ValueError: {e}")
    except Exception as e:
        print(f"  [FAIL]: 意外异常 {type(e).__name__}: {e}")

    # B07-3: run_fault_diagnosis_experiment with eb_n0_db = 10**400
    print("\nB07-3: run_fault_diagnosis_experiment with eb_n0_db=10**400")
    try:
        S = BPSKSimulator(42)
        result = S.run_fault_diagnosis_experiment(100, 10**400, 0.8)
        print(f"  [FAIL]: 应该抛出 ValueError，但返回了结果")
    except TypeError as e:
        print(f"  [FAIL]: 泄漏了 TypeError: {e}")
    except ValueError as e:
        print(f"  [PASS]: 正确抛出 ValueError: {e}")
    except Exception as e:
        print(f"  [FAIL]: 意外异常 {type(e).__name__}: {e}")

    # B07-4: run_fault_diagnosis_experiment with dc_offset = 10**400
    print("\nB07-4: run_fault_diagnosis_experiment with dc_offset=10**400")
    try:
        S = BPSKSimulator(42)
        result = S.run_fault_diagnosis_experiment(100, 10, 10**400)
        print(f"  [FAIL]: 应该抛出 ValueError，但返回了结果")
    except TypeError as e:
        print(f"  [FAIL]: 泄漏了 TypeError: {e}")
    except ValueError as e:
        print(f"  [PASS]: 正确抛出 ValueError: {e}")
    except Exception as e:
        print(f"  [FAIL]: 意外异常 {type(e).__name__}: {e}")


def test_b09_failures():
    """重放 B09 仍然失败的输入"""
    print("\n\n=== B09 缺陷复现 ===\n")

    # B09-1: run_simulation with sample_size=-1
    print("B09-1: run_simulation with sample_size=-1")
    try:
        S = BPSKSimulator(42)
        result = S.run_simulation(100, 10, sample_size=-1)
        actual_len = len(result['rx_samples'])
        if actual_len == 99:
            print(f"  [FAIL]: 返回了 99 个样本（Python 切片 [:- 1]），应该拒绝")
        else:
            print(f"  [FAIL]: 返回了 {actual_len} 个样本，应该拒绝")
    except ValueError as e:
        print(f"  [PASS]: 正确拒绝: {e}")
    except Exception as e:
        print(f"  [FAIL]: 意外异常 {type(e).__name__}: {e}")

    # B09-2: run_simulation with sample_size=0
    print("\nB09-2: run_simulation with sample_size=0")
    try:
        S = BPSKSimulator(42)
        result = S.run_simulation(100, 10, sample_size=0)
        actual_len = len(result['rx_samples'])
        if actual_len == 0:
            print(f"  [FAIL]: 返回了 0 个样本，应该拒绝零")
        else:
            print(f"  [FAIL]: 返回了 {actual_len} 个样本")
    except ValueError as e:
        print(f"  [PASS]: 正确拒绝: {e}")
    except Exception as e:
        print(f"  [FAIL]: 意外异常 {type(e).__name__}: {e}")

    # B09-3: run_simulation with sample_size=True
    print("\nB09-3: run_simulation with sample_size=True")
    try:
        S = BPSKSimulator(42)
        result = S.run_simulation(100, 10, sample_size=True)
        actual_len = len(result['rx_samples'])
        if actual_len == 1:
            print(f"  [FAIL]: True 被当作 1，返回了 1 个样本，应该拒绝 bool")
        else:
            print(f"  [FAIL]: 返回了 {actual_len} 个样本")
    except ValueError as e:
        print(f"  [PASS]: 正确拒绝: {e}")
    except Exception as e:
        print(f"  [FAIL]: 意外异常 {type(e).__name__}: {e}")

    # B09-4: run_simulation with sample_size=1.5 (浮点数)
    print("\nB09-4: run_simulation with sample_size=1.5")
    try:
        S = BPSKSimulator(42)
        result = S.run_simulation(100, 10, sample_size=1.5)
        print(f"  [FAIL]: 应该拒绝浮点数，但返回了结果")
    except TypeError as e:
        print(f"  [FAIL]: 泄漏了 TypeError (切片索引): {e}")
    except ValueError as e:
        print(f"  [PASS]: 正确拒绝: {e}")
    except Exception as e:
        print(f"  [FAIL]: 意外异常 {type(e).__name__}: {e}")

    # B09-5: run_fault_diagnosis_experiment with sample_size=True
    print("\nB09-5: run_fault_diagnosis_experiment with sample_size=True")
    try:
        S = BPSKSimulator(42)
        result = S.run_fault_diagnosis_experiment(100, 10, 0.8, sample_size=True)
        actual_len = len(result['samples']['rx_normal'])
        if actual_len == 1:
            print(f"  [FAIL]: True 被当作 1，返回了 1 个样本，应该拒绝 bool")
        else:
            print(f"  [FAIL]: 返回了 {actual_len} 个样本")
    except ValueError as e:
        print(f"  [PASS]: 正确拒绝: {e}")
    except Exception as e:
        print(f"  [FAIL]: 意外异常 {type(e).__name__}: {e}")


if __name__ == "__main__":
    test_b07_failures()
    test_b09_failures()
    print("\n" + "="*60)
    print("复现完成。所有 [FAIL] 的项目需要修复。")
    print("="*60 + "\n")
