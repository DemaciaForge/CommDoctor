"""
FastAPI后端服务

提供BPSK通信仿真API接口
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator, ValidationError
from bpsk_simulator import BPSKSimulator
from frequency_offset import (
    MAX_UNAMBIGUOUS_OFFSET,
    calculate_bpsk_ber,
    compensate_bpsk_frequency_offset,
    estimate_bpsk_frequency_offset,
    phase_track,
    simulate_bpsk_frequency_offset,
)
from multi_fault import (
    DC_MAGNITUDE,
    FAULT_SCENARIOS,
    FREQUENCY_MAGNITUDE,
    apply_compensation,
    estimate_multi_fault,
    simulate_multi_fault,
)
from typing import Literal
import math
import json
import numpy as np
import secrets
import uuid

app = FastAPI(
    title="CommDoctor API",
    description="数字通信故障诊断教学平台 - BPSK仿真接口",
    version="0.1.0"
)

# F03修复: 添加请求体验证中间件，递归检查非有限数值
def _check_for_nonfinite(obj, path="body"):
    """
    递归检查对象中的所有数值是否为有限数值

    Args:
        obj: 要检查的对象（dict、list或标量）
        path: 当前路径（用于错误定位）

    Returns:
        (is_valid, error_dict) 元组
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            is_valid, error = _check_for_nonfinite(value, f"{path}.{key}")
            if not is_valid:
                return False, error
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            is_valid, error = _check_for_nonfinite(item, f"{path}[{i}]")
            if not is_valid:
                return False, error
    elif isinstance(obj, float):
        # 只检查float类型的非有限值，不检查字符串"NaN"
        if not math.isfinite(obj):
            return False, {
                "type": "value_error",
                "loc": path.split("."),
                "msg": f"Value must be finite (not infinity or NaN), got {str(obj)}"
            }
    # int、str、bool、None都是合法的，不检查
    return True, None

@app.middleware("http")
async def validate_request_body(request: Request, call_next):
    """B组修复：检查请求体中的非有限数值（递归检查所有嵌套结构，覆盖所有POST端点）"""
    if request.method == "POST" and request.url.path in [
        "/api/simulate",
        "/api/fault-diagnosis",
        "/api/apply-threshold",
        "/api/challenges/diagnosis",
        "/api/challenges/repair",
        "/api/stage04/challenges/diagnosis",
        "/api/stage04/challenges/compensate",
        "/api/stage05/challenges/diagnosis",
        "/api/stage05/challenges/compensate"
    ]:
        # P2-01修复：检查 Content-Type，按项目契约返回 422
        content_type = request.headers.get("content-type", "")
        # 允许 application/json 及其变体（如 application/json; charset=utf-8）
        if not content_type.startswith("application/json"):
            return JSONResponse(
                status_code=422,  # 项目契约要求 422 for validation errors
                content={
                    "detail": [{
                        "type": "invalid_content_type",
                        "loc": ["headers", "content-type"],
                        "msg": f"Content-Type must be 'application/json', got '{content_type}'",
                    }]
                }
            )

        try:
            body = await request.body()
            if body:
                # P2修复：处理非法UTF-8编码
                try:
                    body_str = body.decode('utf-8')
                except UnicodeDecodeError as e:
                    return JSONResponse(
                        status_code=422,
                        content={
                            "detail": [{
                                "type": "decode_error",
                                "loc": ["body"],
                                "msg": f"Request body must be valid UTF-8, decode failed at byte {e.start}",
                            }]
                        }
                    )

                data = json.loads(body_str)
                # 检查data是否为字典（拒绝整个请求体为null、数组等非对象类型）
                if not isinstance(data, dict):
                    input_repr = type(data).__name__ if data is not None else "null"
                    return JSONResponse(
                        status_code=422,
                        content={
                            "detail": [{
                                "type": "type_error",
                                "loc": ["body"],
                                "msg": f"Request body must be a JSON object, got {input_repr}",
                            }]
                        }
                    )
                # 递归检查所有嵌套值
                is_valid, error = _check_for_nonfinite(data)
                if not is_valid:
                    return JSONResponse(
                        status_code=422,
                        content={"detail": [error]}
                    )
            # 重建请求体供后续处理
            async def receive():
                return {"type": "http.request", "body": body}
            request._receive = receive
        except json.JSONDecodeError:
            # P2修复：JSON解析失败也返回422
            return JSONResponse(
                status_code=422,
                content={
                    "detail": [{
                        "type": "json_invalid",
                        "loc": ["body"],
                        "msg": "Request body must be valid JSON",
                    }]
                }
            )
        except ValueError as e:
            # P2-B修复：捕获 Python 整数解析限制的 ValueError
            return JSONResponse(
                status_code=422,
                content={
                    "detail": [{
                        "type": "value_error",
                        "loc": ["body"],
                        "msg": f"Invalid value in JSON: {str(e)}",
                    }]
                }
            )

    response = await call_next(request)
    return response

# 配置CORS，允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://localhost:5174",
        "http://127.0.0.1:5173", "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimulationRequest(BaseModel):
    """仿真请求参数"""
    eb_n0_db: float = Field(..., ge=-10, le=30, description="Eb/N0 (dB)")
    n_bits: int = Field(..., ge=100, le=1000000, description="仿真比特数")
    seed: int | None = Field(None, ge=0, description="随机种子（可选，非负整数）")
    sample_size: int = Field(1000, ge=100, le=5000, description="可视化样本数")

    @field_validator('eb_n0_db')
    @classmethod
    def validate_eb_n0(cls, v: float) -> float:
        """验证Eb/N0是有限数值"""
        if not math.isfinite(v):
            raise ValueError("eb_n0_db must be a finite number (not NaN or Infinity)")
        return v

    @field_validator('sample_size', mode='before')
    @classmethod
    def validate_sample_size_type(cls, v):
        """Round6修复：拒绝布尔值和非整数，防止静默转换"""
        # 拒绝布尔值（在 isinstance(int) 之前检查，因为 bool 是 int 的子类）
        if isinstance(v, bool):
            raise ValueError("sample_size must be a true integer, not bool")
        # 拒绝浮点数（即使它看起来像整数）
        if isinstance(v, float):
            raise ValueError("sample_size must be an integer, not float")
        # 拒绝字符串
        if isinstance(v, str):
            raise ValueError("sample_size must be an integer, not string")
        return v


class FaultDiagnosisRequest(BaseModel):
    """故障诊断实验请求参数"""
    eb_n0_db: float = Field(..., ge=-10, le=30, description="Eb/N0 (dB)")
    n_bits: int = Field(..., ge=100, le=1000000, description="仿真比特数")
    dc_offset: float = Field(0.0, ge=-2.0, le=2.0, description="DC偏移值")
    seed: int | None = Field(None, ge=0, description="随机种子（可选，非负整数）")
    sample_size: int = Field(1000, ge=100, le=5000, description="可视化样本数")

    @field_validator('eb_n0_db', 'dc_offset')
    @classmethod
    def validate_finite(cls, v: float) -> float:
        """验证是有限数值"""
        if not math.isfinite(v):
            raise ValueError("Value must be a finite number (not NaN or Infinity)")
        return v

    @field_validator('sample_size', mode='before')
    @classmethod
    def validate_sample_size_type(cls, v):
        """Round6修复：拒绝布尔值和非整数，防止静默转换"""
        if isinstance(v, bool):
            raise ValueError("sample_size must be a true integer, not bool")
        if isinstance(v, float):
            raise ValueError("sample_size must be an integer, not float")
        if isinstance(v, str):
            raise ValueError("sample_size must be an integer, not string")
        return v


class CustomThresholdRequest(BaseModel):
    """自定义门限请求参数"""
    experiment_id: str = Field(..., description="实验ID")
    threshold: float = Field(..., ge=-5.0, le=5.0, description="判决门限")

    @field_validator('threshold')
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        """验证门限是有限数值"""
        if not math.isfinite(v):
            raise ValueError("threshold must be a finite number (not NaN or Infinity)")
        return v


class ChallengeDiagnosisRequest(BaseModel):
    challenge_id: str
    suspected_fault: Literal["dc_offset", "no_fault"]


class ChallengeRepairRequest(BaseModel):
    challenge_id: str
    threshold: float = Field(..., ge=-5.0, le=5.0)

    @field_validator('threshold')
    @classmethod
    def validate_challenge_threshold(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("threshold must be a finite number (not NaN or Infinity)")
        return v


class FrequencyDiagnosisRequest(BaseModel):
    challenge_id: str
    suspected_fault: Literal["frequency_offset", "no_offset"]


class FrequencyCompensationRequest(BaseModel):
    challenge_id: str
    epsilon_hat: float = Field(..., gt=-0.25, lt=0.25, description="normalized cycles per symbol")

    @field_validator('epsilon_hat', mode='before')
    @classmethod
    def validate_epsilon_input(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("epsilon_hat must be a finite real number")
        return value


class MultiFaultDiagnosisRequest(BaseModel):
    challenge_id: str
    suspected_fault: Literal["none", "dc_offset", "frequency_offset", "both"]


class MultiFaultCompensationRequest(BaseModel):
    challenge_id: str
    mode: Literal["dc", "frequency", "both"]
    dc_hat: float = Field(..., ge=-2.0, le=2.0)
    epsilon_hat: float = Field(..., gt=-0.25, lt=0.25)

    @field_validator("dc_hat", "epsilon_hat", mode="before")
    @classmethod
    def validate_multi_fault_input(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("compensation parameters must be finite real numbers")
        return value


class SimulationResponse(BaseModel):
    """仿真响应数据"""
    eb_n0_db: float
    n_bits: int
    n_errors: int
    ber_theoretical: float
    ber_measured: float
    seed: int | None
    rx_samples: list[float]
    tx_symbols_samples: list[float]


@app.get("/")
async def root():
    """API根路径"""
    return {
        "name": "CommDoctor API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    F03修复: 处理验证错误，特别是非有限数值
    避免在错误响应序列化时再次引发异常
    """
    errors = []
    for error in exc.errors():
        # P2-B修复：清理 input 字段（防止 bytes 导致序列化失败）
        if 'input' in error:
            input_val = error['input']
            if isinstance(input_val, bytes):
                # 转换为可读字符串表示
                try:
                    error['input'] = input_val.decode('utf-8', errors='replace')[:100]
                except:
                    error['input'] = f"<bytes: {len(input_val)} bytes>"
            elif not isinstance(input_val, (int, str, bool, type(None), float, list, dict)):
                error['input'] = str(type(input_val).__name__)

        # 检查是否是非有限值导致的错误
        if 'ctx' in error and isinstance(error.get('ctx'), dict):
            ctx = error['ctx']
            # 清理可能包含非有限值的上下文
            cleaned_ctx = {}
            for key, value in ctx.items():
                if isinstance(value, (int, str, bool, type(None))):
                    cleaned_ctx[key] = value
                elif isinstance(value, float):
                    if math.isfinite(value):
                        cleaned_ctx[key] = value
                    else:
                        cleaned_ctx[key] = str(value)  # 转换为字符串
            error['ctx'] = cleaned_ctx
        errors.append(error)

    return JSONResponse(
        status_code=422,
        content={"detail": errors}
    )


@app.post("/api/simulate", response_model=SimulationResponse)
async def run_simulation(request: SimulationRequest):
    """
    运行BPSK通信仿真

    Args:
        request: 仿真参数

    Returns:
        仿真结果

    Raises:
        HTTPException: 参数验证失败或仿真出错
    """
    try:
        # 创建仿真器
        simulator = BPSKSimulator(seed=request.seed)

        # 运行仿真
        result = simulator.run_simulation(
            n_bits=request.n_bits,
            eb_n0_db=request.eb_n0_db,
            sample_size=request.sample_size
        )

        return SimulationResponse(**result)

    except ValueError as e:
        # AUD3-07修复：ValueError表示输入错误，应返回422
        raise HTTPException(status_code=422, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        # 真正的内部错误（RuntimeError等）返回500
        raise HTTPException(status_code=500, detail=f"Simulation error: {str(e)}")


# 用于存储实验数据的简单内存缓存
# E组修复：存储完整的发送比特和接收信号用于配对实验
experiment_cache = {}
MAX_CACHE_SIZE = 10  # F组修复：明确容量限制
challenge_cache = {}
MAX_CHALLENGE_CACHE_SIZE = 20
frequency_challenge_cache = {}
MAX_FREQUENCY_CHALLENGE_CACHE_SIZE = 20
multi_fault_challenge_cache = {}
MAX_MULTI_FAULT_CHALLENGE_CACHE_SIZE = 20


@app.post("/api/fault-diagnosis")
async def run_fault_diagnosis(request: FaultDiagnosisRequest):
    """
    运行故障诊断实验（配对实验）

    Args:
        request: 实验参数

    Returns:
        完整实验结果，包含正常、故障和修复状态

    Raises:
        HTTPException: 参数验证失败或实验出错
    """
    try:
        # 创建仿真器
        simulator = BPSKSimulator(seed=request.seed)

        # 运行故障诊断实验
        result = simulator.run_fault_diagnosis_experiment(
            n_bits=request.n_bits,
            eb_n0_db=request.eb_n0_db,
            dc_offset=request.dc_offset,
            sample_size=request.sample_size
        )

        # 生成实验ID
        import uuid
        experiment_id = str(uuid.uuid4())

        # E组修复：直接使用实验生成的数据进行缓存
        # 提取内部数据（以_开头的键）
        tx_bits_full = result.pop('_tx_bits')
        rx_with_fault_full = result.pop('_rx_with_fault')

        # F组修复：严格控制缓存大小不超过MAX_CACHE_SIZE
        if len(experiment_cache) >= MAX_CACHE_SIZE:
            # FIFO：删除最旧的一个
            oldest_key = next(iter(experiment_cache))
            del experiment_cache[oldest_key]

        # 缓存完整数据用于后续门限调整
        experiment_cache[experiment_id] = {
            'tx_bits': tx_bits_full,
            'rx_with_fault': rx_with_fault_full,
            'eb_n0_db': request.eb_n0_db,
            'n_bits': request.n_bits,
            'dc_offset': request.dc_offset,
            'seed': request.seed
        }

        result['experiment_id'] = experiment_id

        return result

    except ValueError as e:
        # AUD3-07修复：ValueError表示输入错误，应返回422
        raise HTTPException(status_code=422, detail=f"Invalid input: {str(e)}")
    except Exception as e:
        # 真正的内部错误（RuntimeError等）返回500
        raise HTTPException(status_code=500, detail=f"Experiment error: {str(e)}")


@app.post("/api/apply-threshold")
async def apply_custom_threshold(request: CustomThresholdRequest):
    """
    应用自定义判决门限并重新判决

    Args:
        request: 实验ID和门限值

    Returns:
        重新判决的结果

    Raises:
        HTTPException: 实验不存在或参数无效
    """
    try:
        # 从缓存中获取实验数据
        if request.experiment_id not in experiment_cache:
            raise HTTPException(
                status_code=404,
                detail="Experiment not found. Please run a new fault diagnosis experiment."
            )

        exp_data = experiment_cache[request.experiment_id]

        # 创建仿真器并应用门限
        simulator = BPSKSimulator(seed=exp_data['seed'])

        # 使用缓存的数据重新判决
        result = simulator.apply_custom_threshold(
            tx_bits=exp_data['tx_bits'],
            rx_signals=exp_data['rx_with_fault'],
            threshold=request.threshold
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Threshold application error: {str(e)}")


@app.post("/api/challenges")
async def create_diagnostic_challenge():
    """Create a live DC-offset experiment while keeping the injected fault private."""
    try:
        offset = secrets.choice([-0.8, 0.8])
        seed = secrets.randbits(32)
        simulator = BPSKSimulator(seed=seed)
        result = simulator.run_fault_diagnosis_experiment(
            n_bits=10000, eb_n0_db=8.0, dc_offset=offset, sample_size=1000
        )
        tx_bits = result.pop('_tx_bits')
        rx_with_fault = result.pop('_rx_with_fault')
        challenge_id = str(uuid.uuid4())
        if len(challenge_cache) >= MAX_CHALLENGE_CACHE_SIZE:
            del challenge_cache[next(iter(challenge_cache))]
        challenge_cache[challenge_id] = {
            "dc_offset": offset,
            "seed": seed,
            "tx_bits": tx_bits,
            "rx_with_fault": rx_with_fault,
            "result": result,
            "measurement_collected": False,
            "diagnosis_correct": False,
            "repair": None,
        }
        return {
            "challenge_id": challenge_id,
            "status": "observe",
            "objective": "观察同一批 BPSK/AWGN 实验数据，收集证据，判断接收机是否存在 DC 偏移，再尝试修复判决门限。",
            "eb_n0_db": result["eb_n0_db"],
            "n_bits": result["n_bits"],
            "ber_theoretical": result["ber_theoretical"],
            "normal": result["normal"],
            "with_fault": result["with_fault"],
            "samples": result["samples"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Challenge creation error: {str(e)}")


@app.get("/api/challenges/{challenge_id}/measurement")
async def measure_challenge(challenge_id: str):
    challenge = challenge_cache.get(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    evidence = challenge["result"]["diagnosis"]["evidence"]
    challenge["measurement_collected"] = True
    return {
        "status": "evidence_collected",
        "rx_mean": evidence["rx_mean"],
        "std_error": evidence["std_error"],
        "threshold_3sigma": evidence["threshold_3sigma"],
        "n_samples": evidence["n_samples"],
        "noise_std": challenge["result"]["noise_std"],
    }


@app.post("/api/challenges/diagnosis")
async def submit_challenge_diagnosis(request: ChallengeDiagnosisRequest):
    challenge = challenge_cache.get(request.challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if not challenge["measurement_collected"]:
        raise HTTPException(status_code=409, detail="Collect measurement evidence before submitting a diagnosis.")
    actual_fault = challenge["dc_offset"] != 0.0
    is_correct = (request.suspected_fault == "dc_offset") == actual_fault
    challenge["diagnosis_correct"] = is_correct
    if is_correct:
        return {"correct": True, "status": "repair", "message": "判断正确。现在调整判决门限并比较实际 BER。"}
    return {
        "correct": False,
        "status": "diagnose",
        "message": "这个判断尚未得到测量证据支持。请结合接收均值和 3σ 界限重新分析后再试。",
    }


@app.post("/api/challenges/repair")
async def repair_challenge(request: ChallengeRepairRequest):
    challenge = challenge_cache.get(request.challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if not challenge["diagnosis_correct"]:
        raise HTTPException(status_code=409, detail="Submit a correct diagnosis before running the repair experiment.")
    simulator = BPSKSimulator(seed=challenge["seed"])
    try:
        repaired = simulator.apply_custom_threshold(
            challenge["tx_bits"], challenge["rx_with_fault"], request.threshold
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid repair: {str(e)}")
    challenge["repair"] = repaired
    before = challenge["result"]["with_fault"]
    return {
        "status": "repaired",
        "before": before,
        "after": repaired,
        "improved": repaired["n_errors"] < before["n_errors"],
    }


@app.get("/api/challenges/{challenge_id}/feedback")
async def challenge_feedback(challenge_id: str):
    challenge = challenge_cache.get(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if not challenge["diagnosis_correct"]:
        raise HTTPException(status_code=409, detail="Complete the diagnosis before viewing the answer.")
    if challenge["repair"] is None:
        raise HTTPException(status_code=409, detail="Run a threshold repair experiment before viewing feedback.")
    result = challenge["result"]
    repair = challenge["repair"]
    before = result["with_fault"]
    return {
        "status": "complete",
        "actual_fault": {"type": "dc_offset", "dc_offset": challenge["dc_offset"]},
        "diagnosis_correct": challenge["diagnosis_correct"],
        "evidence": result["diagnosis"]["evidence"],
        "noise_std": result["noise_std"],
        "repair": {
            "before": before,
            "after": repair,
            "ideal_threshold_result": result["repaired"],
            "improved": repair["n_errors"] < before["n_errors"],
        },
        "explanation": {
            "fault_mechanism": "DC 偏移将接收样本整体平移：r = s + n + d。接收均值因此偏离零；当偏移方向与符号相反时，零门限会增加误判。",
            "repair_mechanism": "把判决门限移到偏移对应的位置，可以恢复两类 BPSK 符号之间的分界。实际 BER 由本次同一批发送比特与接收样本重新判决计算。",
            "coaching": (
                "你的门限使误码数下降；可以再将它与均值估计及理想门限结果比较。"
                if repair["n_errors"] < before["n_errors"] else
                "本次门限没有降低误码数。可将测得的接收均值作为偏移估计，尝试把门限调到该估计附近，再观察配对 BER。"
            ),
        },
    }


@app.post("/api/stage04/challenges")
async def create_frequency_challenge():
    """Create a complex-baseband BPSK trial with a hidden normalized carrier offset."""
    epsilon = secrets.choice([0.0, 0.02, -0.02])
    seed = secrets.randbits(32)
    try:
        experiment = simulate_bpsk_frequency_offset(
            seed=seed, n_symbols=4096, eb_n0_db=8.0, epsilon=epsilon
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Frequency challenge error: {str(e)}")
    challenge_id = str(uuid.uuid4())
    if len(frequency_challenge_cache) >= MAX_FREQUENCY_CHALLENGE_CACHE_SIZE:
        del frequency_challenge_cache[next(iter(frequency_challenge_cache))]
    frequency_challenge_cache[challenge_id] = {
        **experiment,
        "epsilon": epsilon,
        "seed": seed,
        "eb_n0_db": 8.0,
        "estimate": None,
        "diagnosis_correct": None,
        "diagnosis": None,
        "compensation": None,
    }
    # Sparse real samples keep the payload small while supporting I/Q, phase, and constellation plots.
    stride = 8
    received = experiment["received"][::stride]
    symbols = experiment["symbols"][::stride]
    return {
        "challenge_id": challenge_id,
        "status": "observe",
        "objective": "观察复基带接收信号，估计归一化频偏，判断载波是否偏移，并尝试补偿后比较 BER。",
        "epsilon_unit": "cycles per symbol (Δf·Ts)",
        "estimator_unambiguous_range": [-MAX_UNAMBIGUOUS_OFFSET, MAX_UNAMBIGUOUS_OFFSET],
        "n_symbols": int(experiment["bits"].size),
        "eb_n0_db": 8.0,
        "ber_theoretical": experiment["ber_theoretical"],
        "before": {"ber": experiment["ber"], "n_errors": experiment["n_errors"]},
        "signal": {
            "i": [float(v) for v in received.real],
            "q": [float(v) for v in received.imag],
            "phase_rad": phase_track(experiment["received"], count=512)[::8],
            "constellation": [{"i": float(z.real), "q": float(z.imag)} for z in received],
        },
    }


@app.get("/api/stage04/challenges/{challenge_id}/estimate")
async def estimate_frequency_challenge(challenge_id: str):
    challenge = frequency_challenge_cache.get(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    estimate = estimate_bpsk_frequency_offset(challenge["received"])
    challenge["estimate"] = estimate
    return {
        "status": "estimate_measured",
        "epsilon_hat": estimate,
        "epsilon_unit": "cycles per symbol (Δf·Ts)",
        "unambiguous_range": [-MAX_UNAMBIGUOUS_OFFSET, MAX_UNAMBIGUOUS_OFFSET],
        "decision_deadband": 0.002,
        "method": "BPSK 平方消除 ±1 数据符号后，对平方信号做零填充 FFT，并将谱峰频率折半。",
    }


@app.post("/api/stage04/challenges/diagnosis")
async def diagnose_frequency_challenge(request: FrequencyDiagnosisRequest):
    challenge = frequency_challenge_cache.get(request.challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if challenge["estimate"] is None:
        raise HTTPException(status_code=409, detail="Measure the frequency offset before submitting a diagnosis.")
    # The randomized normal state has exactly zero offset; nonzero states are +/-0.02.
    actual_fault = challenge["epsilon"] != 0.0
    is_correct = (request.suspected_fault == "frequency_offset") == actual_fault
    challenge["diagnosis"] = request.suspected_fault
    challenge["diagnosis_correct"] = is_correct
    if is_correct:
        return {"correct": True, "status": "compensate", "message": "判断正确。使用测得的归一化频偏值尝试补偿。"}
    return {
        "correct": False,
        "status": "diagnose",
        "message": "当前判断与现有相位测量证据不一致。请检查估计值的符号和大小后重试。",
    }


@app.post("/api/stage04/challenges/compensate")
async def compensate_frequency_challenge(request: FrequencyCompensationRequest):
    challenge = frequency_challenge_cache.get(request.challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if challenge["diagnosis_correct"] is not True:
        raise HTTPException(status_code=409, detail="Submit a correct diagnosis before running compensation.")
    try:
        compensated = compensate_bpsk_frequency_offset(challenge["received"], request.epsilon_hat)
        after = calculate_bpsk_ber(challenge["bits"], compensated)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid compensation: {str(e)}")
    challenge["compensation"] = {"epsilon_hat": request.epsilon_hat, **after}
    before = {"ber": challenge["ber"], "n_errors": challenge["n_errors"]}
    return {
        "status": "compensated",
        "before": before,
        "after": after,
        "epsilon_hat": request.epsilon_hat,
        "improved": after["n_errors"] < before["n_errors"],
    }


@app.get("/api/stage04/challenges/{challenge_id}/feedback")
async def frequency_challenge_feedback(challenge_id: str):
    challenge = frequency_challenge_cache.get(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if challenge["diagnosis_correct"] is not True:
        raise HTTPException(status_code=409, detail="Complete the diagnosis before viewing feedback.")
    if challenge["compensation"] is None:
        raise HTTPException(status_code=409, detail="Run a compensation experiment before viewing feedback.")
    compensation = challenge["compensation"]
    estimate = challenge["estimate"]
    before = {"ber": challenge["ber"], "n_errors": challenge["n_errors"]}
    error = estimate - challenge["epsilon"]
    return {
        "status": "complete",
        "actual_fault": {"type": "frequency_offset" if challenge["epsilon"] else "none", "epsilon": challenge["epsilon"]},
        "diagnosis": {"suspected_fault": challenge["diagnosis"], "correct": challenge["diagnosis_correct"]},
        "estimate": {"epsilon_hat": estimate, "epsilon_unit": "cycles per symbol (Δf·Ts)", "error": error},
        "compensation": compensation,
        "ber": {"theoretical": challenge["ber_theoretical"], "before": before, "after": {"ber": compensation["ber"], "n_errors": compensation["n_errors"]}},
        "lesson": {
            "model": "r[n] = a[n]·exp(j·2π·ε·n) + w[n]，本轮初始相位为 0，ε=Δf·Ts，单位是 cycles/symbol；没有给定采样率或符号率，因此不报告 Hz。",
            "estimator": "对 BPSK 接收样本平方可消去 ±1 数据调制，载波频率变为 2ε。零填充 FFT 的谱峰给出平方信号频率，再折半得到 cycles/symbol。无歧义范围为 |ε| < 0.25。",
            "compensation": "对每个样本乘 exp(-j·2π·ε̂·n)，抵消估计的载波相位旋转，再用补偿后实部按零门限判决。",
            "conclusion": (
                "补偿使误码数下降。残余误差来自频偏估计误差和 AWGN。"
                if compensation["n_errors"] < before["n_errors"] else
                "本次补偿未降低误码数；请结合估计误差、噪声和补偿值分析。BER 是有限样本统计量，不保证每次实验都达到理论值。"
            ),
            "limitations": "平方信号频谱估计要求 |ε|<0.25 cycles/symbol；有限长度、频谱峰值插值精度、AWGN 和低 SNR 会带来估计波动。零频偏挑战使用 0.002 cycles/symbol 死区，以避免把测量噪声当作故障。",
        },
    }


@app.post("/api/stage05/challenges")
async def create_multi_fault_challenge():
    """Create a unified complex-baseband challenge with hidden fault combination."""
    scenario = secrets.choice(FAULT_SCENARIOS)
    dc_offset = secrets.choice([DC_MAGNITUDE, -DC_MAGNITUDE]) if scenario in ("dc_offset", "both") else 0.0
    epsilon = secrets.choice([FREQUENCY_MAGNITUDE, -FREQUENCY_MAGNITUDE]) if scenario in ("frequency_offset", "both") else 0.0
    seed = secrets.randbits(32)
    experiment = simulate_multi_fault(
        seed=seed, scenario=scenario, dc_offset=dc_offset, epsilon=epsilon,
        n_symbols=4096, eb_n0_db=8.0,
    )
    challenge_id = str(uuid.uuid4())
    if len(multi_fault_challenge_cache) >= MAX_MULTI_FAULT_CHALLENGE_CACHE_SIZE:
        del multi_fault_challenge_cache[next(iter(multi_fault_challenge_cache))]
    multi_fault_challenge_cache[challenge_id] = {
        **experiment, "scenario": scenario, "dc_offset": dc_offset, "epsilon": epsilon,
        "seed": seed, "measurement": None, "diagnosis": None, "compensation": {},
    }
    received = experiment["received"][::8]
    return {
        "challenge_id": challenge_id, "status": "observe",
        "objective": "观察统一复基带信号，区分无故障、DC 偏移、频率偏移或两者同时存在，并按顺序尝试补偿。",
        "n_symbols": experiment["n_symbols"], "eb_n0_db": experiment["eb_n0_db"],
        "ber_theoretical": experiment["ber_theoretical"], "before": experiment["before"],
        "dc_unit": "接收端 I 路幅度单位", "epsilon_unit": "cycles per symbol (Δf·Ts)",
        "epsilon_unambiguous_range": [-MAX_UNAMBIGUOUS_OFFSET, MAX_UNAMBIGUOUS_OFFSET],
        "signal": {
            "i": [float(v) for v in received.real], "q": [float(v) for v in received.imag],
            "mean_i": float(np.mean(experiment["received"].real)),
            "mean_q": float(np.mean(experiment["received"].imag)),
            "phase_rad": phase_track(experiment["received"], count=512)[::8],
            "constellation": [{"i": float(z.real), "q": float(z.imag)} for z in received],
        },
    }


@app.get("/api/stage05/challenges/{challenge_id}/measurement")
async def measure_multi_fault_challenge(challenge_id: str):
    challenge = multi_fault_challenge_cache.get(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    measured = estimate_multi_fault(challenge["received"])
    challenge["measurement"] = {"dc_hat": measured["dc_hat"], "epsilon_hat": measured["epsilon_hat"]}
    return {
        "status": "measured", "dc_hat": measured["dc_hat"], "epsilon_hat": measured["epsilon_hat"],
        "dc_unit": "接收端 I 路幅度单位", "epsilon_unit": "cycles per symbol (Δf·Ts)",
        "epsilon_unambiguous_range": [-MAX_UNAMBIGUOUS_OFFSET, MAX_UNAMBIGUOUS_OFFSET],
        "dc_method": "接收 I 路实部均值；频偏存在时会有有限样本误差。",
        "epsilon_method": "先减去 DC 测量值，再对平方 BPSK 信号做零填充 FFT 谱峰估计。",
    }


@app.post("/api/stage05/challenges/diagnosis")
async def diagnose_multi_fault_challenge(request: MultiFaultDiagnosisRequest):
    challenge = multi_fault_challenge_cache.get(request.challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if challenge["measurement"] is None:
        raise HTTPException(status_code=409, detail="Collect measurements before submitting a diagnosis.")
    correct = request.suspected_fault == challenge["scenario"]
    challenge["diagnosis"] = {"suspected_fault": request.suspected_fault, "correct": correct}
    if correct:
        return {"correct": True, "status": "compensate", "message": "判断正确。请使用测量值执行分步补偿。"}
    return {"correct": False, "status": "diagnose", "message": "当前判断与测量证据不一致，请继续检查均值和相位轨迹后重试。"}


@app.post("/api/stage05/challenges/compensate")
async def compensate_multi_fault_challenge(request: MultiFaultCompensationRequest):
    challenge = multi_fault_challenge_cache.get(request.challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if challenge["diagnosis"] is None or challenge["diagnosis"]["correct"] is not True:
        raise HTTPException(status_code=409, detail="Submit a correct diagnosis before running compensation.")
    try:
        corrected = apply_compensation(challenge["received"], request.dc_hat, request.epsilon_hat, request.mode)
        result = calculate_bpsk_ber(challenge["bits"], corrected)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    output = {"mode": request.mode, "dc_hat": request.dc_hat, "epsilon_hat": request.epsilon_hat, **result}
    challenge["compensation"][request.mode] = output
    return {
        "status": "compensated", "mode": request.mode,
        "before": challenge["before"], "after": result,
        "dc_hat": request.dc_hat, "epsilon_hat": request.epsilon_hat,
        "all_results": challenge["compensation"],
    }


@app.get("/api/stage05/challenges/{challenge_id}/feedback")
async def multi_fault_challenge_feedback(challenge_id: str):
    challenge = multi_fault_challenge_cache.get(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if challenge["diagnosis"] is None or challenge["diagnosis"]["correct"] is not True:
        raise HTTPException(status_code=409, detail="Complete the diagnosis before viewing feedback.")
    if not challenge["compensation"]:
        raise HTTPException(status_code=409, detail="Run at least one compensation experiment before viewing feedback.")
    measurement = challenge["measurement"]
    return {
        "status": "complete",
        "actual_fault": {"scenario": challenge["scenario"], "dc_offset": challenge["dc_offset"], "epsilon": challenge["epsilon"]},
        "diagnosis": challenge["diagnosis"], "measurement": measurement,
        "compensation": challenge["compensation"],
        "ber": {"theoretical": challenge["ber_theoretical"], "before": challenge["before"], "stages": challenge["compensation"]},
        "lesson": {
            "model": "r[n] = a[n]·exp(j·2π·ε·n) + d + w[n]；d 是频率旋转后加入的接收端 I 路 DC 偏移。",
            "order": "先用 I 路均值估计并移除 d，再对 DC 校正后的平方 BPSK 信号估计 ε，最后按相反方向旋转补偿频偏。",
            "explanation": "仅补偿一种故障时，另一种故障仍保留；联合结果来自同一发送比特、噪声和接收样本。",
            "limitations": "均值和谱峰估计受有限样本、AWGN、参数误差影响；频偏估计范围为 |ε|<0.25 cycles/symbol。",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
