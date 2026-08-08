"""
OCR 服务状态监控路由

提供 OCR 引擎状态、模型信息、健康检查等 API
"""
from fastapi import APIRouter
from app.models.schemas import ApiResponse
from app.services.ocr_service import ocr_service_monitor

router = APIRouter(prefix="/ocr", tags=["OCR 服务监控"])


@router.get("/status", response_model=ApiResponse)
async def get_ocr_status():
    """获取 OCR 服务状态"""
    status = ocr_service_monitor.get_status()
    return ApiResponse(data=status)


@router.get("/model-info", response_model=ApiResponse)
async def get_ocr_model_info():
    """获取 OCR 模型详细信息"""
    model_info = ocr_service_monitor.get_model_info()
    return ApiResponse(data=model_info)


@router.get("/health", response_model=ApiResponse)
async def get_ocr_health():
    """OCR 服务健康检查"""
    status = ocr_service_monitor.get_status()
    healthy = status["engine_ready"] and status["model_info"]["model_files_ready"]
    return ApiResponse(data={
        "healthy": healthy,
        "status": status["status"],
        "engine_ready": status["engine_ready"],
        "model_files_ready": status["model_info"]["model_files_ready"],
        "message": "OCR 服务运行正常" if healthy else "OCR 服务未就绪",
    })


@router.post("/reset-stats", response_model=ApiResponse)
async def reset_ocr_stats():
    """重置 OCR 统计数据"""
    ocr_service_monitor.reset_stats()
    return ApiResponse(data={"success": True, "message": "统计数据已重置"})
