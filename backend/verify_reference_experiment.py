#!/usr/bin/env python3
"""
固定参考实验验证

复现Stage01-Stage02建立的基准实验：
- BPSK调制
- Eb/N0 = 10 dB
- n_bits = 10000
- seed = 42
- DC offset = 0.8

预期结果：
- normal errors  = 0
- fault errors   = 962
- repair errors  = 0
- suggested threshold = 0.7870124722156866
"""
import sys
sys.dont_write_bytecode = True

import numpy as np
from bpsk_simulator import BPSKSimulator


def main():
    print("=" * 70)
    print("固定参考实验验证")
    print("=" * 70)

    # 固定参数
    seed = 42
    n_bits = 10000
    eb_n0_db = 10.0
    dc_offset = 0.8

    print(f"\n参数:")
    print(f"  调制方式: BPSK")
    print(f"  Eb/N0: {eb_n0_db} dB")
    print(f"  比特数: {n_bits}")
    print(f"  随机种子: {seed}")
    print(f"  DC偏移: {dc_offset}")

    # 运行实验
    sim = BPSKSimulator(seed)
    result = sim.run_fault_diagnosis_experiment(n_bits, eb_n0_db, dc_offset)

    print(f"\n实际结果:")
    print(f"  normal errors:  {result['normal']['n_errors']}")
    print(f"  fault errors:   {result['with_fault']['n_errors']}")
    print(f"  repair errors:  {result['repaired']['n_errors']}")
    print(f"\n  suggested threshold: {result['diagnosis']['suggested_threshold']}")

    print(f"\n预期结果:")
    print(f"  normal errors:  0")
    print(f"  fault errors:   962")
    print(f"  repair errors:  0")
    print(f"  suggested threshold: 0.7870124722156866")

    # 验证
    errors_match = (
        result['normal']['n_errors'] == 0 and
        result['with_fault']['n_errors'] == 962 and
        result['repaired']['n_errors'] == 0
    )

    threshold_match = abs(
        result['diagnosis']['suggested_threshold'] - 0.7870124722156866
    ) < 1e-10

    print(f"\n验证:")
    print(f"  错误计数匹配: {'PASS' if errors_match else 'FAIL'}")
    print(f"  建议门限匹配: {'PASS' if threshold_match else 'FAIL'}")

    if errors_match and threshold_match:
        print(f"\n[PASS] 固定参考实验通过")
        return 0
    else:
        print(f"\n[FAIL] 固定参考实验失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())
