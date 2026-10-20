"""复现审计报告中的四个 P2 问题"""
import numpy as np
from fastapi.testclient import TestClient
from main import app
from bpsk_simulator import BPSKSimulator as S

client = TestClient(app)

print("=== P2-01: Content-Type 返回 415 而非契约要求的 422 ===")
response = client.post(
    "/api/simulate",
    content='{"n_bits":100,"eb_n0_db":10,"seed":42,"sample_size":100}',
    headers={"Content-Type": "text/plain"}
)
print(f"Status: {response.status_code} (期望 422, 实际 415)")
print(f"Response: {response.json()}")
print()

print("=== P2-02: object dtype 泄漏 TypeError ===")
try:
    result = S(42).demodulate_bpsk(np.array([0j, 1+0j], dtype=object))
    print(f"意外成功: {result}")
except TypeError as e:
    print(f"TypeError (应该是 ValueError): {e}")
except ValueError as e:
    print(f"正确 ValueError: {e}")
print()

print("=== P2-03: NumPy 整数 Eb/N0 回绕 ===")
result_float = S(42).run_simulation(10000, 10.0)['n_errors']
result_uint8 = S(42).run_simulation(10000, np.uint8(10))['n_errors']
print(f"10.0 (float): {result_float} errors")
print(f"np.uint8(10): {result_uint8} errors")
print(f"期望相同，实际 {'相同' if result_float == result_uint8 else '不同 (BUG!)'}")
print()

result_float_neg = S(42).run_simulation(10000, -128.0)['n_errors']
result_int8_neg = S(42).run_simulation(10000, np.int8(-128))['n_errors']
print(f"-128.0 (float): {result_float_neg} errors")
print(f"np.int8(-128): {result_int8_neg} errors")
print(f"期望相同，实际 {'相同' if result_float_neg == result_int8_neg else '不同 (BUG!)'}")
print()

print("=== P2-04: sample_size 接受非法值 ===")
try:
    result_neg = S(42).run_simulation(100, 10, sample_size=-1)
    print(f"sample_size=-1: 返回 {len(result_neg['rx_samples'])} 个样本 (应拒绝)")
except ValueError as e:
    print(f"sample_size=-1: 正确 ValueError: {e}")

try:
    result_zero = S(42).run_simulation(100, 10, sample_size=0)
    print(f"sample_size=0: 返回 {len(result_zero['rx_samples'])} 个样本 (应拒绝)")
except ValueError as e:
    print(f"sample_size=0: 正确 ValueError: {e}")

try:
    result_bool = S(42).run_simulation(100, 10, sample_size=True)
    print(f"sample_size=True: 返回 {len(result_bool['rx_samples'])} 个样本 (应拒绝)")
except ValueError as e:
    print(f"sample_size=True: 正确 ValueError: {e}")

try:
    result_float = S(42).run_simulation(100, 10, sample_size=1.5)
    print(f"sample_size=1.5: 意外成功")
except TypeError as e:
    print(f"sample_size=1.5: TypeError (应该是 ValueError): {e}")
except ValueError as e:
    print(f"sample_size=1.5: 正确 ValueError: {e}")
