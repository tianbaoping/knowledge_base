from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.models.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    FileDetailResponse,
    ApiResponse,
)
from app.services.import_service import import_service

router = APIRouter(prefix="/kb", tags=["知识库管理"])


class ChunkEditRequest(BaseModel):
    text: str


@router.post("", response_model=ApiResponse)
async def create_knowledge_base(data: KnowledgeBaseCreate):
    result = await import_service.create_knowledge_base(data.name, data.description)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(data=result)


@router.get("", response_model=ApiResponse)
async def list_knowledge_bases():
    kbs = await import_service.list_knowledge_bases()
    return ApiResponse(data=kbs)


@router.get("/{kb_name}", response_model=ApiResponse)
async def get_knowledge_base(kb_name: str):
    detail = await import_service.get_knowledge_base_detail(kb_name)
    if not detail:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return ApiResponse(data=detail)


@router.delete("/{kb_name}", response_model=ApiResponse)
async def delete_knowledge_base(kb_name: str):
    result = await import_service.delete_knowledge_base(kb_name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(data=result)


@router.get("/{kb_name}/files", response_model=ApiResponse)
async def list_files(kb_name: str):
    files = await import_service.list_files(kb_name)
    return ApiResponse(data=files)


@router.delete("/{kb_name}/files/{file_id}", response_model=ApiResponse)
async def delete_file(kb_name: str, file_id: int):
    result = await import_service.delete_file(kb_name, file_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(data=result)


@router.put("/{kb_name}/chunks/{chunk_id}", response_model=ApiResponse)
async def update_chunk(kb_name: str, chunk_id: str, data: ChunkEditRequest):
    """编辑切片内容：重新向量化并更新"""
    result = await import_service.update_chunk(kb_name, chunk_id, data.text)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(data=result)


@router.delete("/{kb_name}/chunks/{chunk_id}", response_model=ApiResponse)
async def delete_chunk(kb_name: str, chunk_id: str):
    """删除单个切片"""
    result = await import_service.delete_chunk(kb_name, chunk_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(data=result)