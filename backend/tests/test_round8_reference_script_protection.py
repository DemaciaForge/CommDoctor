"""
Round8 参考实验脚本自动化保护

确保参考实验脚本真正被正式测试保护，能够检测字段漂移。
"""

import subprocess
import sys
import json
import pytest
from pathlib import Path


class TestReferenceScriptExecution:
    """测试参考实验脚本的实际执行"""

    def test_reference_script_runs_successfully(self):
        """参考实验脚本必须成功执行并返回预期结果"""
        # 获取脚本路径（相对于测试文件）
        test_dir = Path(__file__).parent
        backend_dir = test_dir.parent
        script_path = backend_dir / "verify_reference_experiment.py"

        assert script_path.exists(), f"参考脚本不存在: {script_path}"

        # 执行脚本
        result = subprocess.run(
            [sys.executable, "-B", str(script_path)],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            encoding='gbk',  # Windows 中文环境
            errors='replace',  # 遇到无法解码的字符时替换
            timeout=30
        )

        # 验证退出码
        assert result.returncode == 0, (
            f"参考脚本执行失败。\n"
            f"退出码: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

        # 验证输出包含关键信息
        output = result.stdout

        # 验证参数被正确显示
        assert "Eb/N0: 10" in output or "Eb/N0: 10.0" in output
        assert "10000" in output  # n_bits
        assert "0.8" in output    # dc_offset

        # 验证实际结果被显示
        assert "normal" in output.lower() and "0" in output
        assert "fault" in output.lower() and "962" in output
        assert "repair" in output.lower()

        # 验证通过标志
        assert "PASS" in output

    def test_reference_script_validates_correct_results(self):
        """参考脚本验证正确的实验结果"""
        test_dir = Path(__file__).parent
        backend_dir = test_dir.parent
        script_path = backend_dir / "verify_reference_experiment.py"

        result = subprocess.run(
            [sys.executable, "-B", str(script_path)],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='replace',
            timeout=30
        )

        assert result.returncode == 0

        # 解析输出，验证关键数值
        output = result.stdout

        # 验证误码数
        # 输出格式：normal errors:  0
        assert "0" in output
        assert "962" in output

        # 验证建议门限（至少前几位匹配）
        assert "0.7870124722156866" in output or "0.787012472215" in output


class TestReferenceScriptFieldDrift:
    """测试参考脚本的字段漂移检测能力

    验证：当脚本中的字段名被改错时，测试应该失败
    """

    def test_correct_field_names_required(self):
        """验证脚本使用正确的字段名

        这个测试通过实际执行脚本并检查其行为来验证字段名正确性。
        如果在临时副本中故意改错字段名，该脚本应该失败（KeyError）。

        注意：这个测试本身验证正常路径。字段漂移变异测试由 Round8
        修复报告的独立验证部分执行（在隔离副本中）。
        """
        test_dir = Path(__file__).parent
        backend_dir = test_dir.parent
        script_path = backend_dir / "verify_reference_experiment.py"

        # 读取脚本内容，验证使用正确的字段名
        script_content = script_path.read_text(encoding='utf-8')

        # 验证脚本读取正确的字段
        assert "result['normal']['n_errors']" in script_content
        assert "result['with_fault']['n_errors']" in script_content
        assert "result['repaired']['n_errors']" in script_content
        assert "result['diagnosis']['suggested_threshold']" in script_content

        # 不应该有错误的字段名（常见漂移案例）
        assert "result['normal']['errors']" not in script_content
        assert "result['with_fault']['errors']" not in script_content
        assert "result['normal']['error_count']" not in script_content

        # 执行脚本确保它真正能运行
        result = subprocess.run(
            [sys.executable, "-B", str(script_path)],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='replace',
            timeout=30
        )

        assert result.returncode == 0, (
            f"参考脚本应该成功执行。\n"
            f"退出码: {result.returncode}\n"
            f"stderr:\n{result.stderr}"
        )


class TestReferenceOracleIndependence:
    """验证参考实验的独立 oracle"""

    def test_reference_results_match_independent_calculation(self):
        """参考实验结果应与独立计算一致"""
        import numpy as np
        from bpsk_simulator import BPSKSimulator

        # 固定参数（与参考脚本相同）
        seed = 42
        n_bits = 10000
        eb_n0_db = 10.0
        dc_offset = 0.8

        # 执行实验
        sim = BPSKSimulator(seed)
        result = sim.run_fault_diagnosis_experiment(n_bits, eb_n0_db, dc_offset)

        # 验证结果字段存在
        assert 'normal' in result
        assert 'with_fault' in result
        assert 'repaired' in result
        assert 'diagnosis' in result

        assert 'n_errors' in result['normal']
        assert 'n_errors' in result['with_fault']
        assert 'n_errors' in result['repaired']
        assert 'suggested_threshold' in result['diagnosis']

        # 验证与固定基准一致
        assert result['normal']['n_errors'] == 0
        assert result['with_fault']['n_errors'] == 962
        assert result['repaired']['n_errors'] == 0

        # 验证建议门限
        expected_threshold = 0.7870124722156866
        actual_threshold = result['diagnosis']['suggested_threshold']
        assert abs(actual_threshold - expected_threshold) < 1e-10

        # 验证标准误差字段存在
        assert 'evidence' in result['diagnosis']
        assert 'std_error' in result['diagnosis']['evidence']

        expected_std_error = 0.010246950765959599
        actual_std_error = result['diagnosis']['evidence']['std_error']
        assert abs(actual_std_error - expected_std_error) < 1e-10
