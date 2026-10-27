"""
FastAPI后端服务

提供BPSK通信仿真API接口
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator, ValidationError
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
from phase_offset import simulate_phase_offset, estimate_phase, compensate_phase, measure_ber
from triple_fault import SCENARIOS as STAGE07_SCENARIOS, simulate_triple_fault, estimate_triple, compensate_triple
from timing_sync import (
    MAX_EB_N0_DB as STAGE08_MAX_EB_N0_DB,
    MIN_EB_N0_DB as STAGE08_MIN_EB_N0_DB,
    MAX_PAYLOAD_SYMBOLS as STAGE08_MAX_PAYLOAD_SYMBOLS,
    MIN_PAYLOAD_SYMBOLS as STAGE08_MIN_PAYLOAD_SYMBOLS,
    SAMPLES_PER_SYMBOL as STAGE08_SPS,
    SPAN_SYMBOLS as STAGE08_SPAN,
    ROLLOFF as STAGE08_ROLLOFF,
    TIMING_PHASES as STAGE08_PHASES,
    create_experiment as create_timing_experiment,
    ber_for_phase as stage08_ber_for_phase,
)
from multipath_equalization import (
    MAX_DELAY_SYMBOLS as STAGE09_MAX_DELAY_SYMBOLS,
    MAX_EB_N0_DB as STAGE09_MAX_EB_N0_DB,
    MAX_PAYLOAD_SYMBOLS as STAGE09_MAX_PAYLOAD_SYMBOLS,
    MIN_EB_N0_DB as STAGE09_MIN_EB_N0_DB,
    MIN_PAYLOAD_SYMBOLS as STAGE09_MIN_PAYLOAD_SYMBOLS,
    PILOT_SYMBOLS as STAGE09_PILOT_SYMBOLS,
    SAMPLES_PER_SYMBOL as STAGE09_SPS,
    create_experiment as create_multipath_experiment,
    equalize as equalize_multipath,
    estimate_channel as estimate_multipath_channel,
)
from convolutional_coding import (
    MAX_SWEEP_INFORMATION_BITS,
    MAX_SWEEP_TOTAL_INFORMATION_BITS,
    eb_n0_scan_points,
    run_eb_n0_sweep,
    run_experiment as run_stage10_experiment,
    encode_frame as encode_stage10_frame,
    decode_frame as decode_stage10_frame,
)
from interleaving import (
    MAX_DIMENSION as STAGE11_MAX_DIMENSION,
    MAX_BLOCK_BITS as STAGE11_MAX_BLOCK_BITS,
    interleave_bits as stage11_interleave_bits,
    deinterleave_bits as stage11_deinterleave_bits,
    apply_burst_errors as stage11_apply_burst_errors,
)
from typing import Literal
import math
import json
import numpy as np
import secrets
import uuid
import logging

app = FastAPI(
    title="CommDoctor API",
    description="数字通信故障诊断教学平台 - BPSK仿真接口",
    version="0.1.0"
)
logger = logging.getLogger(__name__)

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
        "/api/stage05/challenges/compensate",
        "/api/stage06/challenges/diagnosis",
        "/api/stage06/challenges/compensate",
        "/api/stage07/challenges/diagnosis",
        "/api/stage07/challenges/compensate",
        "/api/stage08/challenges/diagnosis",
        "/api/stage08/challenges/compensate",
        "/api/stage09/experiments",
        "/api/stage10/experiments",
        "/api/stage11/experiments",
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


class Stage06CreateRequest(BaseModel):
    scenario: Literal["normal", "phase", "phase_positive", "phase_negative"]


class Stage06DiagnosisRequest(BaseModel):
    challenge_id: str
    suspected_fault: Literal["none", "phase_offset"]


class Stage06CompensationRequest(BaseModel):
    challenge_id: str
    compensation_deg: float = Field(..., ge=-180, le=180)

    @field_validator("compensation_deg", mode="before")
    @classmethod
    def validate_phase_compensation(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("compensation_deg must be a finite real number")
        return value


class Stage07DiagnosisRequest(BaseModel):
    challenge_id: str
    suspected_fault: Literal["none", "dc", "frequency", "phase", "dc_frequency", "dc_phase", "frequency_phase", "triple"]


class Stage07CompensationRequest(BaseModel):
    challenge_id: str
    mode: Literal["dc", "frequency", "phase", "joint"]
    dc_hat: float = Field(..., ge=-2, le=2)
    epsilon_hat: float = Field(..., gt=-0.25, lt=0.25)
    phi_hat_deg: float = Field(..., ge=-180, le=180)

    @field_validator("dc_hat", "epsilon_hat", "phi_hat_deg", mode="before")
    @classmethod
    def validate_stage07_values(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value):
            raise ValueError("compensation values must be finite real numbers")
        return value


class Stage08CreateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    mode: Literal["guided", "challenge"] = "challenge"
    timing_offset_samples: StrictInt | None = None
    eb_n0_db: float = Field(8.0, ge=STAGE08_MIN_EB_N0_DB, le=STAGE08_MAX_EB_N0_DB)
    n_payload_symbols: StrictInt = Field(1024, ge=STAGE08_MIN_PAYLOAD_SYMBOLS, le=STAGE08_MAX_PAYLOAD_SYMBOLS)
    seed: StrictInt | None = Field(None, ge=0, le=2**32 - 1)

    @field_validator("eb_n0_db", mode="before")
    @classmethod
    def validate_stage08_snr(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("eb_n0_db must be a finite real number")
        return value

    @model_validator(mode="after")
    def validate_stage08_mode(self):
        if self.mode == "guided" and self.timing_offset_samples is None:
            raise ValueError("guided mode requires timing_offset_samples")
        if self.timing_offset_samples is not None and self.timing_offset_samples not in STAGE08_PHASES:
            raise ValueError("timing_offset_samples must be from -7 through 7")
        if self.mode == "challenge" and (self.timing_offset_samples is not None or self.seed is not None):
            raise ValueError("challenge mode does not accept a timing offset or seed")
        return self


class Stage08DiagnosisRequest(BaseModel):
    challenge_id: str
    suspected_fault: Literal["timing_offset", "no_timing_offset"]


class Stage08CompensationRequest(BaseModel):
    challenge_id: str
    compensation_samples: StrictInt = Field(..., ge=-7, le=7)


class Stage09CreateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    mode: Literal["guided", "challenge"] = "guided"
    eb_n0_db: float = Field(8.0, ge=STAGE09_MIN_EB_N0_DB, le=STAGE09_MAX_EB_N0_DB)
    n_payload_symbols: StrictInt = Field(512, ge=STAGE09_MIN_PAYLOAD_SYMBOLS, le=STAGE09_MAX_PAYLOAD_SYMBOLS)
    seed: StrictInt | None = Field(None, ge=0, le=2**32 - 1)
    path_delays_samples: list[StrictInt] | None = None
    path_gains: list[float] | None = None

    @field_validator("eb_n0_db", mode="before")
    @classmethod
    def validate_stage09_snr(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("eb_n0_db must be a finite real number")
        return value

    @field_validator("path_gains", mode="before")
    @classmethod
    def validate_stage09_gains(cls, value):
        if value is None:
            return value
        if not isinstance(value, list) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
            raise ValueError("path_gains must contain finite real numbers")
        return value

    @model_validator(mode="after")
    def validate_stage09_mode(self):
        if self.mode == "challenge" and (self.seed is not None or self.path_delays_samples is not None or self.path_gains is not None):
            raise ValueError("challenge mode does not accept seed or true channel parameters")
        return self


class Stage09EqualizeRequest(BaseModel):
    model_config = {"extra": "forbid"}
    algorithm: Literal["zf", "mmse"]


class Stage10CreateRequest(BaseModel):
    """Bounded request for one deterministic Stage10 coding experiment."""
    model_config = {"extra": "forbid"}

    n_information_bits: StrictInt = Field(256, ge=1, le=4096)
    eb_n0_db: float = Field(4.0, ge=-10.0, le=30.0)
    seed: StrictInt = Field(2026, ge=0, le=2**32 - 1)
    include_details: bool = False

    @field_validator("eb_n0_db", mode="before")
    @classmethod
    def validate_stage10_snr(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("eb_n0_db must be a finite real number")
        return value

    @field_validator("include_details", mode="before")
    @classmethod
    def validate_stage10_details_flag(cls, value):
        if not isinstance(value, bool):
            raise ValueError("include_details must be a boolean")
        return value

    @model_validator(mode="after")
    def validate_detail_limit(self):
        if self.include_details and self.n_information_bits > 256:
            raise ValueError("include_details is limited to 256 information bits; disable details for larger experiments")
        return self


class Stage11CreateRequest(BaseModel):
    """Bounded single-frame Stage11 burst/interleaving experiment."""
    model_config = {"extra": "forbid"}

    n_information_bits: StrictInt = Field(64, ge=1, le=4096)
    seed: StrictInt = Field(2026, ge=0, le=2**32 - 1)
    rows: StrictInt = Field(4, ge=1, le=STAGE11_MAX_DIMENSION)
    columns: StrictInt = Field(4, ge=1, le=STAGE11_MAX_DIMENSION)
    burst_start: StrictInt = Field(0, ge=0)
    burst_length: StrictInt = Field(8, ge=0)

    @model_validator(mode="after")
    def validate_stage11_frame(self):
        if self.rows * self.columns > STAGE11_MAX_BLOCK_BITS:
            raise ValueError(f"矩阵容量不能超过 {STAGE11_MAX_BLOCK_BITS} 位")
        encoded_length = 2 * (self.n_information_bits + 2)
        block_size = self.rows * self.columns
        transmitted_length = ((encoded_length + block_size - 1) // block_size) * block_size
        if transmitted_length > 2 * (4096 + 2) + STAGE11_MAX_BLOCK_BITS:
            raise ValueError("填充后的传输帧超过计算上限")
        if self.burst_length > transmitted_length:
            raise ValueError(f"突发长度不能超过传输帧长度 {transmitted_length}")
        if self.burst_start > transmitted_length or self.burst_start + self.burst_length > transmitted_length:
            raise ValueError(f"突发区间必须完全位于传输索引 0 至 {transmitted_length - 1} 内")
        return self


class Stage10BerSweepRequest(BaseModel):
    """Bounded request for an independent, reproducible Eb/N0 sweep."""
    model_config = {"extra": "forbid"}

    start_db: float = Field(0.0, ge=-10.0, le=30.0)
    stop_db: float = Field(10.0, ge=-10.0, le=30.0)
    step_db: float = Field(2.0, gt=0.0, le=40.0)
    n_information_bits: StrictInt = Field(2048, ge=1, le=MAX_SWEEP_INFORMATION_BITS)
    seed: StrictInt = Field(2026, ge=0, le=2**32 - 1)

    @field_validator("start_db", "stop_db", "step_db", mode="before")
    @classmethod
    def validate_sweep_float(cls, value, info):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{info.field_name} must be a finite real number")
        return value

    @model_validator(mode="after")
    def validate_sweep_grid_and_budget(self):
        points = eb_n0_scan_points(self.start_db, self.stop_db, self.step_db)
        total = len(points) * self.n_information_bits
        if total > MAX_SWEEP_TOTAL_INFORMATION_BITS:
            raise ValueError(f"sweep may process at most {MAX_SWEEP_TOTAL_INFORMATION_BITS} information bits total")
        return self


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
stage06_challenge_cache = {}
stage07_challenge_cache = {}
stage08_challenge_cache = {}
stage09_experiment_cache = {}


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


@app.post("/api/stage06/challenges")
async def create_stage06_challenge(request: Stage06CreateRequest):
    if request.scenario == "normal":
        phase = 0.0
    elif request.scenario == "phase_positive":
        phase = secrets.choice([math.pi/4, math.pi/3])
    elif request.scenario == "phase_negative":
        phase = secrets.choice([-math.pi/4, -math.pi/3])
    else:
        phase = secrets.choice([-math.pi/4, math.pi/4, -math.pi/3, math.pi/3])
    experiment = simulate_phase_offset(seed=secrets.randbits(32), phase_rad=phase)
    challenge_id = str(uuid.uuid4())
    if len(stage06_challenge_cache) >= 20:
        del stage06_challenge_cache[next(iter(stage06_challenge_cache))]
    stage06_challenge_cache[challenge_id] = {**experiment, "scenario": "phase_offset" if phase != 0 else "none", "measurement": None, "diagnosis": None, "compensation": None}
    samples = experiment["received"][::8]
    return {"challenge_id": challenge_id, "status": "observe", "objective": "从实际 I/Q 信号和星座图识别恒定载波相位偏移。",
            "n_symbols": experiment["n_symbols"], "eb_n0_db": experiment["eb_n0_db"], "before": experiment["before"],
            "phase_unit": "degrees (°); internal calculations use radians", "signal": {
                "i": samples.real.tolist(), "q": samples.imag.tolist(),
                "constellation": [{"i": float(z.real), "q": float(z.imag)} for z in samples]}}


@app.get("/api/stage06/challenges/{challenge_id}/measurement")
async def measure_stage06_challenge(challenge_id: str):
    challenge = stage06_challenge_cache.get(challenge_id)
    if challenge is None: raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    estimate = estimate_phase(challenge["received"])
    challenge["measurement"] = estimate
    return {"status": "measured", "phase_hat_rad": estimate, "phase_hat_deg": math.degrees(estimate), "unit": "degrees (°)",
            "method": "0.5 × arg(sum(r[n]^2)); BPSK data signs cancel; normalized to [-90°, 90°)."}


@app.post("/api/stage06/challenges/diagnosis")
async def diagnose_stage06_challenge(request: Stage06DiagnosisRequest):
    challenge = stage06_challenge_cache.get(request.challenge_id)
    if challenge is None: raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if challenge["measurement"] is None: raise HTTPException(status_code=409, detail="Measure the received signal before diagnosis.")
    correct = request.suspected_fault == challenge["scenario"]
    challenge["diagnosis"] = {"suspected_fault": request.suspected_fault, "correct": correct}
    return {"correct": correct, "status": "compensate" if correct else "diagnose", "message": "判断正确。可以提交你的补偿角度。" if correct else "判断暂不正确，请结合相位估计和星座方向重新判断。"}


@app.post("/api/stage06/challenges/compensate")
async def compensate_stage06_challenge(request: Stage06CompensationRequest):
    challenge = stage06_challenge_cache.get(request.challenge_id)
    if challenge is None: raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if not challenge["diagnosis"] or not challenge["diagnosis"]["correct"]: raise HTTPException(status_code=409, detail="Submit a correct diagnosis before compensation.")
    corrected = compensate_phase(challenge["received"], math.radians(request.compensation_deg))
    after = measure_ber(challenge["bits"], corrected)
    challenge["compensation"] = {"compensation_deg": request.compensation_deg, "after": after, "constellation": [{"i": float(z.real), "q": float(z.imag)} for z in corrected[::8]]}
    return {"status": "compensated", "before": challenge["before"], "after": after, "compensation_deg": request.compensation_deg,
            "constellation": challenge["compensation"]["constellation"]}


@app.get("/api/stage06/challenges/{challenge_id}/feedback")
async def stage06_challenge_feedback(challenge_id: str):
    challenge = stage06_challenge_cache.get(challenge_id)
    if challenge is None: raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if not challenge["diagnosis"] or not challenge["diagnosis"]["correct"] or not challenge["compensation"]: raise HTTPException(status_code=409, detail="Complete diagnosis and compensation before feedback.")
    actual_deg = math.degrees(challenge["phase_rad"])
    estimate_deg = math.degrees(challenge["measurement"])
    return {"status": "complete", "actual_fault": {"scenario": challenge["scenario"], "phase_deg": actual_deg}, "diagnosis": challenge["diagnosis"],
            "estimate_deg": estimate_deg, "estimate_error_deg": estimate_deg-actual_deg, "compensation": challenge["compensation"],
            "before": challenge["before"], "after": challenge["compensation"]["after"],
            "lesson": {"model": "r[n] = a[n]·exp(jφ) + w[n]；φ 用弧度计算，界面使用角度。", "principle": "补偿将每个复样本乘以 exp(-jφ̂)，把星座旋回 BPSK 实轴。", "limits": "平方估计器存在 π 相位歧义，输出范围 [-90°, 90°)；本实验故障限制在 ±60°。接近 ±90° 或低信噪比时估计可能不稳定。补偿前后使用相同发送比特和噪声。"}}


@app.post("/api/stage07/challenges")
async def create_stage07_challenge():
    scenario = secrets.choice(tuple(STAGE07_SCENARIOS))
    experiment = simulate_triple_fault(seed=secrets.randbits(32), scenario=scenario)
    challenge_id = str(uuid.uuid4())
    if len(stage07_challenge_cache) >= 20: del stage07_challenge_cache[next(iter(stage07_challenge_cache))]
    stage07_challenge_cache[challenge_id] = {**experiment, "measurement": None, "diagnosis": None, "compensation": {}}
    z=experiment["received"]; sample=z[::8]
    return {"challenge_id":challenge_id,"status":"observe","n_symbols":experiment["n_symbols"],"eb_n0_db":experiment["eb_n0_db"],"before":experiment["before"],
            "units":{"dc":"I-channel amplitude","epsilon":"cycles per symbol (Δf·Ts), not Hz","phi":"degrees (°); internal radians"},
            "signal":{"i":sample.real.tolist(),"q":sample.imag.tolist(),"mean_i":float(np.mean(z.real)),"mean_q":float(np.mean(z.imag)),
                      "phase_rad":phase_track(z,count=512)[::8],"constellation":[{"i":float(v.real),"q":float(v.imag)} for v in sample]}}


@app.get("/api/stage07/challenges/{challenge_id}/measurement")
async def measure_stage07_challenge(challenge_id:str):
    challenge=stage07_challenge_cache.get(challenge_id)
    if challenge is None: raise HTTPException(status_code=404,detail="Challenge not found or expired. Start a new challenge.")
    try: measured=estimate_triple(challenge["received"])
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc))
    challenge["measurement"]=measured
    measured.update({"dc_unit":"I-channel amplitude","epsilon_unit":"cycles per symbol (Δf·Ts)","phi_unit":"degrees (°)",
                     "dc_method":"接收 I 路样本均值；频偏/相位及有限样本数据会造成估计误差。",
                     "frequency_method":"减去 I 均值后，对平方 BPSK 信号进行零填充 FFT 频谱峰估计；|ε|<0.25。",
                     "phase_method":"去 DC 并按估计频偏反旋后计算 0.5·arg(sum(r²))，归一化到 [-90°,90°)。"})
    return {"status":"measured",**measured}


@app.post("/api/stage07/challenges/diagnosis")
async def diagnose_stage07_challenge(request:Stage07DiagnosisRequest):
    challenge=stage07_challenge_cache.get(request.challenge_id)
    if challenge is None: raise HTTPException(status_code=404,detail="Challenge not found or expired. Start a new challenge.")
    if challenge["measurement"] is None: raise HTTPException(status_code=409,detail="Measure the received signal before diagnosis.")
    correct=request.suspected_fault==challenge["scenario"]
    challenge["diagnosis"]={"suspected_fault":request.suspected_fault,"correct":correct}
    return {"correct":correct,"status":"compensate" if correct else "diagnose","message":"组合判断正确，可以进行分步补偿。" if correct else "判断不匹配，请结合三类测量证据后重试。"}


@app.post("/api/stage07/challenges/compensate")
async def compensate_stage07_challenge(request:Stage07CompensationRequest):
    challenge=stage07_challenge_cache.get(request.challenge_id)
    if challenge is None: raise HTTPException(status_code=404,detail="Challenge not found or expired. Start a new challenge.")
    if not challenge["diagnosis"] or not challenge["diagnosis"]["correct"]: raise HTTPException(status_code=409,detail="Submit a correct diagnosis before compensation.")
    try:
        corrected=compensate_triple(challenge["received"],request.dc_hat,request.epsilon_hat,math.radians(request.phi_hat_deg),request.mode)
        result=calculate_bpsk_ber(challenge["bits"],corrected)
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc))
    constellation=[{"i":float(v.real),"q":float(v.imag)} for v in corrected[::8]]
    output={"mode":request.mode,"dc_hat":request.dc_hat,"epsilon_hat":request.epsilon_hat,"phi_hat_deg":request.phi_hat_deg,**result}
    challenge["compensation"][request.mode]=output
    return {"status":"compensated","before":challenge["before"],"after":result,"all_results":challenge["compensation"],"constellation":constellation}


@app.get("/api/stage07/challenges/{challenge_id}/feedback")
async def stage07_challenge_feedback(challenge_id:str):
    challenge=stage07_challenge_cache.get(challenge_id)
    if challenge is None: raise HTTPException(status_code=404,detail="Challenge not found or expired. Start a new challenge.")
    if not challenge["diagnosis"] or not challenge["diagnosis"]["correct"] or not challenge["compensation"]: raise HTTPException(status_code=409,detail="Complete diagnosis and at least one compensation before feedback.")
    m=challenge["measurement"]; truth={"scenario":challenge["scenario"],"dc":challenge["dc"],"epsilon":challenge["epsilon"],"phi_deg":math.degrees(challenge["phi"])}
    errors={"dc":m["dc_hat"]-challenge["dc"],"epsilon":m["epsilon_hat"]-challenge["epsilon"],"phi_deg":m["phi_hat_deg"]-truth["phi_deg"]}
    return {"status":"complete","actual_fault":truth,"diagnosis":challenge["diagnosis"],"measurement":m,"estimate_errors":errors,
            "before":challenge["before"],"compensation":challenge["compensation"],
            "lesson":{"model":"r[n]=a[n]exp(j(2πεn+φ))+d+w[n]。先注入相位和逐符号频率旋转，再叠加 I 路 DC，最后叠加复 AWGN。","order":"测量 DC 均值并校正，再从平方 BPSK 估计频偏并反旋，最后从校正信号估计恒定相位。各估计误差会向后传播。","limitations":"DC 均值受有限随机数据影响；频偏平方谱估计适用 |ε|<0.25 cycles/symbol；恒定相位存在 π 歧义，估计限制为 [-90°,90°)。低信噪比、短样本及残余 DC 会影响联合估计。BER 是同一批样本上的硬判决统计，可能变差。"}}


@app.post("/api/stage08/challenges")
async def create_stage08_challenge(request: Stage08CreateRequest):
    offset = request.timing_offset_samples if request.mode == "guided" else secrets.choice(STAGE08_PHASES)
    seed = request.seed if request.mode == "guided" and request.seed is not None else secrets.randbits(32)
    try:
        experiment = create_timing_experiment(seed=seed, timing_offset_samples=offset,
            eb_n0_db=request.eb_n0_db, n_payload_symbols=request.n_payload_symbols)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Stage08 experiment: {exc}")
    challenge_id = str(uuid.uuid4())
    if len(stage08_challenge_cache) >= 20:
        del stage08_challenge_cache[next(iter(stage08_challenge_cache))]
    stage08_challenge_cache[challenge_id] = {**experiment, "mode": request.mode,
        "measurement": None, "diagnosis": None, "compensations": []}
    preview = experiment["preview"]
    return {
        "challenge_id": challenge_id, "status": "observe", "mode": request.mode,
        "objective": "观察过采样波形，利用训练序列估计静态符号定时偏移，诊断后选择采样相位并比较 BER。",
        "parameters": {"samples_per_symbol": STAGE08_SPS, "rolloff": STAGE08_ROLLOFF,
            "span_symbols": STAGE08_SPAN, "timing_offset_unit": "samples; positive means delayed",
            "symbol_time_unit": "Ts", "eb_n0_db": experiment["eb_n0_db"],
            "n_payload_symbols": experiment["n_payload_symbols"], "pilot_symbols": 64,
            "pilot_bits": experiment["pilot_bits"].astype(int).tolist()},
        "waveform": {"sample_indices": preview["sample_indices"].astype(int).tolist(),
            "time_symbols": preview["time_symbols"].astype(float).tolist(),
            "transmit": preview["tx"].astype(float).tolist(),
            "receive": experiment["rx_waveform"][preview["sample_indices"]].astype(float).tolist(),
            "matched_filter": preview["matched"].astype(float).tolist(),
            "group_delay_samples": experiment["group_delay_samples"],
            "pilot_start_symbol": experiment["pilot_start_symbol"],
            "payload_start_symbol": experiment["payload_start_symbol"]},
    }


@app.get("/api/stage08/challenges/{challenge_id}/measurement")
async def measure_stage08_challenge(challenge_id: str):
    challenge = stage08_challenge_cache.get(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    measurement = challenge["initial_measurement"]
    challenge["measurement"] = measurement
    return {"status": "measured", "timing_offset_hat_samples": measurement["phase_samples"],
        "timing_offset_hat_symbols": measurement["phase_samples"] / STAGE08_SPS,
        "unit": "sample phases; 1 sample = Ts/16",
        "method": "已知训练序列内部 48 个符号的匹配滤波输出均方误差有限网格搜索。",
        "pilot_symbols_used": measurement["pilot_symbols_used"], "candidate_scores": measurement["scores"]}


@app.post("/api/stage08/challenges/diagnosis")
async def diagnose_stage08_challenge(request: Stage08DiagnosisRequest):
    challenge = stage08_challenge_cache.get(request.challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if challenge["measurement"] is None:
        raise HTTPException(status_code=409, detail="Measure the timing offset before submitting a diagnosis.")
    actual_fault = challenge["timing_offset_samples"] != 0
    correct = (request.suspected_fault == "timing_offset") == actual_fault
    challenge["diagnosis"] = {"suspected_fault": request.suspected_fault, "correct": correct}
    return {"correct": correct, "status": "compensate" if correct else "diagnose",
        "message": "诊断正确。选择采样相位并观察同一接收数据上的 BER。" if correct else
        "判断与测量证据不一致，请结合候选评分和波形重新判断。"}


@app.post("/api/stage08/challenges/compensate")
async def compensate_stage08_challenge(request: Stage08CompensationRequest):
    challenge = stage08_challenge_cache.get(request.challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if challenge["diagnosis"] is None or challenge["diagnosis"]["correct"] is not True:
        raise HTTPException(status_code=409, detail="Submit a correct diagnosis before running timing compensation.")
    before = challenge["initial_ber"]
    try:
        after = stage08_ber_for_phase(challenge["matched"], challenge["payload_bits"],
            challenge["payload_start_symbol"], request.compensation_samples, challenge["group_delay_samples"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid compensation: {exc}")
    result = {"before": before, "after": after, "improved": after["n_errors"] < before["n_errors"]}
    challenge["compensations"].append(result)
    return {"status": "compensated", **result}


@app.get("/api/stage08/challenges/{challenge_id}/feedback")
async def stage08_challenge_feedback(challenge_id: str):
    challenge = stage08_challenge_cache.get(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found or expired. Start a new challenge.")
    if challenge["diagnosis"] is None or challenge["diagnosis"]["correct"] is not True:
        raise HTTPException(status_code=409, detail="Complete the diagnosis before viewing feedback.")
    if not challenge["compensations"]:
        raise HTTPException(status_code=409, detail="Run at least one compensation experiment before viewing feedback.")
    last = challenge["compensations"][-1]
    offset = challenge["timing_offset_samples"]
    estimate = challenge["measurement"]["phase_samples"]
    return {"status": "complete", "actual_fault": {"type": "timing_offset" if offset else "none",
        "timing_offset_samples": offset, "timing_offset_symbols": offset / STAGE08_SPS},
        "seed": challenge["seed"], "diagnosis": challenge["diagnosis"],
        "measurement": {"estimate_samples": estimate, "error_samples": estimate - offset,
            "candidate_scores": challenge["measurement"]["scores"]}, "compensation": last,
        "effective_payload": {"n_compared": last["after"]["n_compared"],
            "symbol_start": last["after"]["payload_symbol_start"],
            "symbol_end_exclusive": last["after"]["payload_symbol_end_exclusive"]},
        "lesson": {"model": "aₖ∈{-1,+1}; x[n]=Σₖaₖh[n-kS], r[n]=x[n-q]+w[n]。正 q 表示接收波形延迟 q 个样本。",
            "estimator": "对已知 pilot 的 15 个候选采样相位计算 MSE，取本候选网格内最小值；这不是普遍最优同步器。",
            "compensation": "只改变采样索引 D+kS+q_c；发送比特、噪声、接收数组和 payload 索引保持不变。",
            "filtering": "Tx/Rx RRC 均为 129 taps，单级群延迟 64 samples，合计 128 samples。BER 不包含 pilot 或 guard，只比较固定 payload 区间。",
            "conclusion": "本次采样相位补偿降低了误码数。" if last["improved"] else
                "本次选择没有降低误码数；估计误差或当前采样相位可能仍不合适。BER 如实来自本轮固定数据。",
            "limitations": "采样相位分辨率为 Ts/16；静态偏移范围为 -7 到 +7 samples。低 Eb/N0 下 pilot MSE 可能选错相位；本阶段不处理载波偏移、时钟漂移、多径或分数延迟。"}}


@app.post("/api/stage09/experiments")
async def create_stage09_experiment(request: Stage09CreateRequest):
    seed = request.seed if request.mode == "guided" and request.seed is not None else secrets.randbelow(2**32)
    delays = request.path_delays_samples if request.mode == "guided" and request.path_delays_samples is not None else [0, STAGE09_SPS]
    gains = request.path_gains if request.mode == "guided" and request.path_gains is not None else [1.0, 0.7]
    try:
        experiment = create_multipath_experiment(seed=seed, eb_n0_db=request.eb_n0_db,
            n_payload_symbols=request.n_payload_symbols, path_delays_samples=delays, path_gains=gains)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Stage09 experiment: {exc}")
    experiment_id = str(uuid.uuid4())
    if len(stage09_experiment_cache) >= 20:
        del stage09_experiment_cache[next(iter(stage09_experiment_cache))]
    stage09_experiment_cache[experiment_id] = {**experiment, "mode": request.mode, "status": "created"}
    layout = experiment["layout"]
    preview_indices = experiment["preview_indices"]
    matched_indices = np.minimum(preview_indices + layout.group_delay_samples, len(experiment["matched"]) - 1)
    response = {
        "experiment_id": experiment_id, "status": "created", "mode": request.mode,
        "objective": "观察两径传播如何把相邻 BPSK 符号叠加到接收采样，再用训练序列拟合短窗均衡器。",
        "parameters": {"samples_per_symbol": STAGE09_SPS, "rolloff": 0.35, "span_symbols": 8,
            "eb_n0_db": experiment["eb_n0_db"], "n_payload_symbols": experiment["n_payload_symbols"],
            "pilot_symbols": STAGE09_PILOT_SYMBOLS, "equalizer_taps": 5, "path_count": len(experiment["path_gains"])},
        "channel": {"impulse": experiment["channel_impulse"].tolist()} if request.mode == "guided" else {"path_count": len(experiment["path_gains"])},
        "layout": {"pilot_start_symbol": layout.pilot_start_symbol, "pilot_length": layout.pilot_length,
            "payload_start_symbol": layout.payload_start_symbol, "payload_end_symbol_exclusive": layout.payload_start_symbol + layout.payload_length,
            "group_delay_samples": layout.group_delay_samples, "tx_filter_delay_samples": layout.tx_filter_delay,
            "rx_filter_delay_samples": layout.rx_filter_delay, "channel_reference_delay_samples": layout.channel_reference_delay,
            "payload_sample_indices": [int(v) for v in layout.payload_sample_indices]},
        "raw_ber": experiment["raw_ber"],
        "waveform": {"sample_indices": [int(v) for v in preview_indices],
            "transmit": experiment["tx_waveform"][preview_indices].tolist(),
            "receive": experiment["rx_waveform"][preview_indices].tolist(),
            "matched_filter": experiment["matched"][matched_indices].tolist()},
        "pilot": {"length": STAGE09_PILOT_SYMBOLS, "bits": experiment["pilot_bits"].tolist()},
    }
    if request.mode == "guided":
        response["seed"] = seed
        response["parameters"].update({"path_delays_samples": [int(v) for v in experiment["path_delays_samples"]],
            "path_gains": [float(v) for v in experiment["path_gains"]], "noise_variance": experiment["noise_variance"]})
    stage09_experiment_cache[experiment_id]["response"] = response
    return response


def _stage09_get(experiment_id: str) -> dict:
    experiment = stage09_experiment_cache.get(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found or expired. Start a new experiment.")
    return experiment


@app.get("/api/stage09/experiments/{experiment_id}/estimate")
async def estimate_stage09_experiment(experiment_id: str):
    experiment = _stage09_get(experiment_id)
    try:
        result = estimate_multipath_channel(experiment)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid measurement: {exc}")
    experiment["status"] = "estimated"
    return result


@app.post("/api/stage09/experiments/{experiment_id}/equalize")
async def equalize_stage09_experiment(experiment_id: str, request: Stage09EqualizeRequest):
    experiment = _stage09_get(experiment_id)
    try:
        result = equalize_multipath(experiment, request.algorithm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid equalization: {exc}")
    experiment["status"] = "equalized"
    return {"status": "equalized", **result, "raw": experiment["raw_ber"]}


@app.get("/api/stage09/experiments/{experiment_id}/feedback")
async def stage09_experiment_feedback(experiment_id: str):
    experiment = _stage09_get(experiment_id)
    if not experiment.get("equalizations"):
        raise HTTPException(status_code=409, detail="Run at least one equalizer before viewing the review.")
    layout = experiment["layout"]
    results = experiment["equalizations"]
    best = min((result["n_errors"], name) for name, result in results.items())[1]
    raw_errors = experiment["raw_ber"]["n_errors"]
    best_result = results[best]
    return {"status": "complete", "results": results, "raw": experiment["raw_ber"],
        "effective_payload": {"n_compared": layout.payload_length, "symbol_start": layout.payload_start_symbol,
            "symbol_end_exclusive": layout.payload_start_symbol + layout.payload_length,
            "sample_indices": [int(v) for v in layout.payload_sample_indices]},
        "lesson": {"model": "发射信号 x[n]=Σ aₖh[n−kS]，多径接收 r[n]=Σ cₗx[n−dₗ]+w[n]。延迟回波把较早符号的能量带到当前符号时刻，造成 ISI。",
            "equalizer": "5 抽头对称符号窗以 64 个已知 pilot 建立回归；ZF 解 XᵀXw=Xᵀt，MMSE 解 (XᵀX+λI)w=Xᵀt，λ=噪声方差。两者只用 pilot 拟合。",
            "tradeoff": "ZF 追求抵消估计到的符号间干扰，但病态信道可能放大噪声。MMSE 加正则项，在残余 ISI 与噪声放大之间折中。",
            "conclusion": f"本次 {best.upper()} 的误码为 {best_result['n_errors']}/{best_result['n_compared']}，原始判决为 {raw_errors}/{experiment['raw_ber']['n_compared']}。结果来自同一接收数组和固定 payload 索引；均衡不保证每次都改善 BER。",
            "limitations": "静态实数 BPSK、整数符号延迟（16 samples 的倍数）、固定 RRC 与短窗线性均衡器；不包含分数延迟、时变信道、载波偏移或编码。单进程内存缓存最多保留 20 个实验。"}}


@app.post("/api/stage10/experiments")
async def create_stage10_experiment(request: Stage10CreateRequest):
    """Run a complete, stateless Stage10 experiment through the production core."""
    try:
        result = run_stage10_experiment(
            n_information_bits=request.n_information_bits,
            eb_n0_db=request.eb_n0_db,
            seed=request.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Stage10 experiment: {exc}") from exc
    except Exception as exc:  # keep implementation details in server logs only
        logger.exception("Stage10 experiment failed")
        raise HTTPException(status_code=500, detail="Stage10 experiment could not be completed. Please retry.") from exc

    full = result.to_dict()
    n = result.information_bit_count
    window = n if request.include_details else min(n, 64)
    # A truncated payload preview stops before the next payload bit; only a
    # complete frame preview includes the two encoded termination inputs.
    coded_window = min(result.encoded_bit_count, 2 * window + (2 * result.tail_bit_count if window == n else 0))
    if result.uncoded_errors < result.decoded_information_errors:
        comparison = "本次固定样本中，未编码信息误码较少；卷积编码不保证每次实验都改善结果。"
    elif result.uncoded_errors > result.decoded_information_errors:
        comparison = "本次固定样本中，译码后的信息误码较少；单次实验不能证明普遍性能优势。"
    else:
        comparison = "本次固定样本中，两条链路的信息误码数相同；噪声和有限帧长会影响单次结果。"

    return {
        "parameters": {
            "n_information_bits": n,
            "eb_n0_db": result.eb_n0_db,
            "seed": result.random_seed,
            "include_details": request.include_details,
        },
        "code": {
            "constraint_length": 3,
            "generators_octal": [7, 5],
            "output_order": ["g0", "g1"],
            "rate": result.code_rate,
            "termination": "two_zero_tail_bits",
            "decoder": "terminated_hard_decision_viterbi",
        },
        "energy": {
            "eb_info": result.eb_info,
            "eb_n0_db": result.eb_n0_db,
            "noise_variance": result.noise_variance,
            "noise_std": result.noise_std,
            "uncoded_symbol_energy": result.eb_info,
            "coded_symbol_energy": result.code_rate * result.eb_info,
        },
        "lengths": {
            "information_bits": n,
            "tail_bits": result.tail_bit_count,
            "encoded_bits": result.encoded_bit_count,
            "encoded_symbols": result.encoded_symbol_count,
            "decoded_information_bits": result.decoded_information_length,
            "effective_frame_rate": n / result.encoded_symbol_count,
        },
        "results": {
            "uncoded_information": {
                "errors": result.uncoded_errors,
                "compared": n,
                "ber": result.uncoded_ber,
            },
            "coded_channel": {
                "errors": result.coded_channel_errors,
                "compared": result.encoded_bit_count,
                "ber": result.coded_channel_ber,
                "includes_tail": True,
            },
            "decoded_information": {
                "errors": result.decoded_information_errors,
                "compared": n,
                "ber": result.decoded_information_ber,
                "correctly_recovered": result.decoded_information_errors == 0,
                "decoded_tail_bits": list(result.decoded_tail_bits),
                "tail_counted": False,
            },
        },
        "details": {
            "included": request.include_details,
            "window_information_bits": window,
            "window_encoded_bits": coded_window,
            "truncated": window < n,
            "information_bits": list(full["information_bits"][:window]),
            "encoded_bits": list(full["encoded_bits"][:coded_window]),
            "uncoded_received": list(full["uncoded_received"][:window]),
            "uncoded_hard_decisions": list(full["uncoded_hard_decisions"][:window]),
            "coded_received": list(full["coded_received"][:coded_window]),
            "coded_hard_decisions": list(full["coded_hard_decisions"][:coded_window]),
            "decoded_information_bits": list(full["decoded_information_bits"][:window]),
        },
        "teaching": {
            "encoding": "每个信息位经 K=3、(7,5) 卷积编码生成两个码位；末尾两个零尾位用于回到零状态。",
            "channel": "BPSK 符号经过实值 AWGN；编码与未编码链路按相同信息位 Eb/N0 和能量预算比较。",
            "decoding": "硬判决把接收样本映射为 0/1；Viterbi 在四状态 trellis 上累积 Hamming 路径度量并选择终止于零状态的最优路径。",
            "comparison": comparison,
            "limitation": "BER 来自本次固定的有限样本。零误码表示本帧未观察到错误，不代表总体误码率永远为零。",
        },
    }


@app.post("/api/stage11/experiments")
async def create_stage11_experiment(request: Stage11CreateRequest):
    """Run one bounded Stage11 production coding/interleaving/burst experiment."""
    try:
        rng = np.random.default_rng(request.seed)
        information_bits = tuple(int(value) for value in rng.integers(0, 2, size=request.n_information_bits))
        encoding = encode_stage10_frame(information_bits)
        interleaved = stage11_interleave_bits(encoding.encoded_bits, request.rows, request.columns)
        burst = stage11_apply_burst_errors(
            interleaved.bits,
            request.burst_length,
            start=request.burst_start,
        )
        restored = stage11_deinterleave_bits(
            burst.bits, interleaved.valid_length, request.rows, request.columns,
        )
        decoded = decode_stage10_frame(restored, request.n_information_bits)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Stage11 experiment: {exc}") from exc
    except Exception as exc:
        logger.exception("Stage11 experiment failed")
        raise HTTPException(status_code=500, detail="Stage11 experiment could not be completed. Please retry.") from exc

    coded_error_indices = tuple(index for index, (expected, actual) in enumerate(zip(encoding.encoded_bits, restored)) if expected != actual)
    decoded_error_indices = tuple(index for index, (expected, actual) in enumerate(zip(information_bits, decoded.information_bits)) if expected != actual)
    post_interleave_error_indices = tuple(
        index for index, (expected, actual) in enumerate(zip(interleaved.bits, burst.bits)) if expected != actual
    )
    burst_to_coded = {
        str(transmission_index): interleaved.output_sources[transmission_index]
        for transmission_index in burst.flipped_positions
    }
    information_error_count = len(decoded_error_indices)
    return {
        "parameters": {
            "n_information_bits": request.n_information_bits,
            "seed": request.seed,
            "rows": request.rows,
            "columns": request.columns,
            "burst_start": request.burst_start,
            "burst_length": request.burst_length,
        },
        "code": {
            "constraint_length": 3,
            "generators_octal": [7, 5],
            "output_order": ["g0", "g1"],
            "rate": encoding.code_rate,
            "tail_bits": encoding.tail_bits,
            "decoder": "terminated_hard_decision_viterbi",
        },
        "lengths": {
            "information_bits": len(information_bits),
            "tail_bits": encoding.tail_bits,
            "encoded_bits": len(encoding.encoded_bits),
            "valid_interleaved_bits": interleaved.valid_length,
            "transmitted_bits": interleaved.padded_length,
            "padding_bits": interleaved.pad_count,
            "decoded_information_bits": len(decoded.information_bits),
        },
        "interleaver": {
            "rows": request.rows,
            "columns": request.columns,
            "block_bits": request.rows * request.columns,
            "output_sources": list(interleaved.output_sources),
        },
        "channel": {
            "burst_start": burst.start,
            "burst_length": burst.length,
            "flipped_positions": list(burst.flipped_positions),
            "flipped_count": burst.flipped_count,
            "transmission_error_count": len(post_interleave_error_indices),
            "transmission_error_indices": list(post_interleave_error_indices),
            "transmission_to_coded_index": burst_to_coded,
        },
        "results": {
            "coded_error_indices_after_deinterleave": list(coded_error_indices),
            "coded_error_count": len(coded_error_indices),
            "decoded_information_error_indices": list(decoded_error_indices),
            "information_error_count": information_error_count,
            "information_ber": information_error_count / len(information_bits),
            "information_ber_errors": information_error_count,
            "information_ber_denominator": len(information_bits),
            "corrected_all_information_errors": information_error_count == 0,
        },
        "details": {
            "information_bits": list(information_bits),
            "encoded_bits": list(encoding.encoded_bits),
            "interleaved_bits": list(interleaved.bits),
            "transmitted_bits": list(burst.bits),
            "deinterleaved_bits": list(restored),
            "decoded_information_bits": list(decoded.information_bits),
        },
        "teaching": {
            "mapping": "交织按行写入矩形块、按列读出；传输坐标与编码坐标通过来源表逐位对应。",
            "burst": "突发错误只在传输序列的连续区间内翻转；填充位参与传输但不进入信息 BER。",
            "conclusion": (
                f"本次注入 {burst.flipped_count} 个传输错误，反交织后有 {len(coded_error_indices)} 个有效编码位错误，"
                f"Viterbi 后有 {information_error_count}/{len(information_bits)} 个信息位错误。"
            ),
            "limitation": "交织把传输坐标重新映射到编码坐标，但单次突发落点可能落在相近编码位置或填充位；不保证每次都改善 BER。",
        },
    }


@app.post("/api/stage10/ber-sweep")
async def create_stage10_ber_sweep(request: Stage10BerSweepRequest):
    """Run a bounded set of Stage10 production experiments across Eb/N0."""
    try:
        return run_eb_n0_sweep(
            start_db=request.start_db,
            stop_db=request.stop_db,
            step_db=request.step_db,
            n_information_bits=request.n_information_bits,
            seed=request.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Stage10 BER sweep: {exc}") from exc
    except Exception as exc:
        logger.exception("Stage10 BER sweep failed")
        raise HTTPException(status_code=500, detail="Stage10 BER sweep could not be completed. Please retry.") from exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
