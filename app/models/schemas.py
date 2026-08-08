from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="知识库名称")
    description: Optional[str] = Field(default="", description="知识库描述")


class KnowledgeBaseResponse(BaseModel):
    id: int
    name: str
    description: str = ""
    created_at: str
    updated_at: str
    status: str = "active"
    doc_count: int = 0
    vector_count: int = 0
    storage_size: int = 0


class FileUploadResponse(BaseModel):
    file_id: int
    file_name: str
    status: str
    message: str


class FileDetailResponse(BaseModel):
    id: int
    kb_name: str
    file_name: str
    file_path: str
    file_size: int = 0
    file_format: str = ""
    chunk_count: int = 0
    vector_count: int = 0
    import_status: str = ""
    uploaded_at: str


class ImportTaskResponse(BaseModel):
    id: int
    kb_name: str
    task_type: str
    total_files: int = 0
    success_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    status: str = "pending"
    created_at: str
    finished_at: Optional[str] = None
    error_message: str = ""


class ImportTaskFileResponse(BaseModel):
    id: int
    task_id: int
    file_name: str
    file_size: int = 0
    file_format: str = ""
    status: str = "pending"
    error_reason: str = ""
    processed_at: Optional[str] = None


class ImportTaskDetail(BaseModel):
    task: ImportTaskResponse
    files: List[ImportTaskFileResponse] = []


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="搜索问题")
    kb_name: Optional[str] = Field(default=None, description="知识库名称，为空则搜索所有")
    top_k: int = Field(default=5, ge=1, le=50, description="返回结果数量")
    score_threshold: float = Field(default=0.3, ge=0.0, le=1.0, description="相似度阈值")
    use_reranker: Optional[bool] = Field(default=None, description="是否使用Reranker重排序，默认开启")
    reranker_recall_top_k: Optional[int] = Field(default=None, ge=1, le=200, description="Reranker第一阶段向量召回数量，默认10，需>=top_k")


class SearchResultItem(BaseModel):
    chunk_id: str
    text: str
    score: float
    metadata: dict = {}


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem] = []
    total: int = 0
    retrieval_info: Optional[dict] = None


class SystemStatus(BaseModel):
    app_status: str = "running"
    qdrant_status: str = "unknown"
    qdrant_collections: List[str] = []
    uptime_seconds: int = 0
    total_kbs: int = 0
    total_files: int = 0
    total_vectors: int = 0
    today_imports: int = 0


class ResourceInfo(BaseModel):
    disk_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    vector_storage_size: int = 0
    remaining_storage: int = 0


class ErrorLogResponse(BaseModel):
    id: int
    error_type: str
    module: str
    file_name: str
    content: str
    stack_trace: str
    created_at: str


class ApiResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Any = None


class MCPToolCall(BaseModel):
    tool_name: str
    arguments: dict = {}


class MCPSearchResult(BaseModel):
    content: str
    metadata: dict = {}
    score: float = 0.0