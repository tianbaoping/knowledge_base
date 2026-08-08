from fastapi import APIRouter, HTTPException, Header, Depends
from typing import Optional
from app.models.schemas import (
    SearchRequest,
    SearchResponse,
    ApiResponse,
    SystemStatus,
    MCPToolCall,
)
from app.services.mcp_service import mcp_service

router = APIRouter(prefix="/mcp", tags=["MCP协议服务"])


def verify_auth(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少鉴权信息")
    parts = authorization.split(" ")
    if len(parts) == 2 and parts[0] == "Bearer":
        api_key = parts[1]
    else:
        api_key = authorization
    if not mcp_service.verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="鉴权失败")
    return True


@router.post("/search", response_model=SearchResponse)
async def knowledge_search(request: SearchRequest, _: bool = Depends(verify_auth)):
    result = await mcp_service.search(
        query=request.query,
        kb_name=request.kb_name,
        top_k=request.top_k,
        score_threshold=request.score_threshold,
        use_reranker=request.use_reranker,
        reranker_recall_top_k=request.reranker_recall_top_k,
    )
    results = result.get("results", [])
    search_items = []
    for r in results:
        payload = r.get("payload", {})
        search_items.append({
            "chunk_id": str(r.get("id", "")),
            "text": payload.get("text", ""),
            "score": r.get("score", 0.0),
            "metadata": {
                "file_name": payload.get("file_name", ""),
                "kb_name": payload.get("kb_name", ""),
                "file_id": payload.get("file_id"),
                "index": payload.get("index"),
                "collection": r.get("collection", ""),
            },
        })
    return SearchResponse(
        query=result.get("query", request.query),
        results=search_items,
        total=result.get("total", 0),
        retrieval_info=result.get("retrieval_info"),
    )


@router.get("/knowledge-bases", response_model=ApiResponse)
async def list_knowledge_bases(_: bool = Depends(verify_auth)):
    result = await mcp_service.list_knowledge_bases()
    return ApiResponse(data=result)


@router.get("/knowledge-bases/{kb_name}/documents/{chunk_id}", response_model=ApiResponse)
async def get_document_detail(
    kb_name: str,
    chunk_id: str,
    _: bool = Depends(verify_auth),
):
    result = await mcp_service.get_document_detail(kb_name, chunk_id)
    if not result:
        raise HTTPException(status_code=404, detail="文档不存在")
    return ApiResponse(data=result)


@router.get("/health", response_model=ApiResponse)
async def health_check():
    result = await mcp_service.health_check()
    return ApiResponse(data=result)


@router.get("/tools", response_model=ApiResponse)
async def get_tools(_: bool = Depends(verify_auth)):
    tools = await mcp_service.get_mcp_tools()
    return ApiResponse(data=tools)


@router.post("/tool/call", response_model=ApiResponse)
async def call_tool(
    payload: MCPToolCall,
    _: bool = Depends(verify_auth),
):
    tool_name = payload.tool_name
    arguments = payload.arguments or {}
    try:
        # ---- 检索类 ----
        if tool_name == "knowledge_search":
            result = await mcp_service.search(
                query=arguments.get("query", ""),
                kb_name=arguments.get("kb_name"),
                top_k=arguments.get("top_k", 5),
                score_threshold=arguments.get("score_threshold", 0.3),
                use_reranker=arguments.get("use_reranker"),
                reranker_recall_top_k=arguments.get("reranker_recall_top_k"),
            )
            return ApiResponse(data=result)

        elif tool_name == "get_document_detail":
            result = await mcp_service.get_document_detail(
                arguments.get("kb_name", ""),
                arguments.get("chunk_id", ""),
            )
            return ApiResponse(data=result)

        # ---- 知识库管理类 ----
        elif tool_name == "list_knowledge_bases":
            result = await mcp_service.list_knowledge_bases()
            return ApiResponse(data=result)

        elif tool_name == "create_knowledge_base":
            result = await mcp_service.create_knowledge_base(
                arguments.get("name", ""),
                arguments.get("description", ""),
            )
            return ApiResponse(data=result)

        elif tool_name == "get_knowledge_base_detail":
            result = await mcp_service.get_knowledge_base_detail(
                arguments.get("kb_name", ""),
            )
            return ApiResponse(data=result)

        elif tool_name == "delete_knowledge_base":
            result = await mcp_service.delete_knowledge_base(
                arguments.get("kb_name", ""),
            )
            return ApiResponse(data=result)

        # ---- 文件管理类 ----
        elif tool_name == "list_files":
            result = await mcp_service.list_files(
                arguments.get("kb_name", ""),
            )
            return ApiResponse(data=result)

        elif tool_name == "delete_file":
            result = await mcp_service.delete_file(
                arguments.get("kb_name", ""),
                arguments.get("file_id", 0),
            )
            return ApiResponse(data=result)

        elif tool_name == "get_file_chunks":
            result = await mcp_service.get_file_chunks(
                arguments.get("kb_name", ""),
                arguments.get("file_id", 0),
            )
            return ApiResponse(data=result)

        # ---- 切片管理类 ----
        elif tool_name == "update_chunk":
            result = await mcp_service.update_chunk(
                arguments.get("kb_name", ""),
                arguments.get("chunk_id", ""),
                arguments.get("text", ""),
            )
            return ApiResponse(data=result)

        elif tool_name == "delete_chunk":
            result = await mcp_service.delete_chunk(
                arguments.get("kb_name", ""),
                arguments.get("chunk_id", ""),
            )
            return ApiResponse(data=result)

        # ---- 文件导入类 ----
        elif tool_name == "import_single_file":
            result = await mcp_service.import_single_file(
                kb_name=arguments.get("kb_name", ""),
                file_path=arguments.get("file_path", ""),
                chunk_size=arguments.get("chunk_size"),
                chunk_overlap=arguments.get("chunk_overlap"),
            )
            return ApiResponse(data=result)

        elif tool_name == "import_batch_files":
            result = await mcp_service.import_batch_files(
                kb_name=arguments.get("kb_name", ""),
                file_paths=arguments.get("file_paths", []),
                chunk_size=arguments.get("chunk_size"),
                chunk_overlap=arguments.get("chunk_overlap"),
            )
            return ApiResponse(data=result)

        elif tool_name == "import_zip_file":
            result = await mcp_service.import_zip_file(
                kb_name=arguments.get("kb_name", ""),
                zip_path=arguments.get("zip_path", ""),
                chunk_size=arguments.get("chunk_size"),
                chunk_overlap=arguments.get("chunk_overlap"),
            )
            return ApiResponse(data=result)

        # ---- 导入任务类 ----
        elif tool_name == "list_import_tasks":
            result = await mcp_service.list_import_tasks(
                arguments.get("kb_name"),
            )
            return ApiResponse(data=result)

        elif tool_name == "get_import_task":
            result = await mcp_service.get_import_task(
                arguments.get("task_id", 0),
            )
            return ApiResponse(data=result)

        # ---- 系统监控类 ----
        elif tool_name == "service_health_check":
            result = await mcp_service.health_check()
            return ApiResponse(data=result)

        elif tool_name == "get_system_status":
            result = await mcp_service.get_system_status()
            return ApiResponse(data=result)

        elif tool_name == "get_resource_info":
            result = await mcp_service.get_resource_info()
            return ApiResponse(data=result)

        else:
            raise HTTPException(status_code=400, detail=f"未知工具: {tool_name}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))