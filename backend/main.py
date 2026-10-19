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
import math
import json
import numpy as np

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
        "/api/apply-threshold"
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
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
