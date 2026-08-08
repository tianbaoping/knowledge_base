from fastapi import APIRouter, Query
from typing import Optional
from app.models.schemas import ApiResponse
from app.services.monitor_service import monitor_service

router = APIRouter(prefix="/monitor", tags=["系统监控"])


@router.get("/status", response_model=ApiResponse)
async def get_system_status():
    status = await monitor_service.get_system_status()
    return ApiResponse(data=status)


@router.get("/resource", response_model=ApiResponse)
async def get_resource_info():
    info = await monitor_service.get_resource_info()
    return ApiResponse(data=info)


@router.get("/errors", response_model=ApiResponse)
async def get_error_logs(
    error_type: Optional[str] = Query(None, description="错误类型筛选"),
    limit: int = Query(50, ge=1, le=500),
):
    logs = await monitor_service.get_error_logs(error_type, limit)
    return ApiResponse(data=logs)


@router.get("/logs", response_model=ApiResponse)
async def get_system_logs(
    level: Optional[str] = Query(None, description="日志级别筛选"),
    limit: int = Query(50, ge=1, le=500),
):
    logs = await monitor_service.get_system_logs(level, limit)
    return ApiResponse(data=logs)