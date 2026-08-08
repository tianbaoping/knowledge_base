# 知识库管理系统 - Docker 部署指南

## 支持的 CPU 架构

| 架构 | Docker Platform | 常见设备 |
|------|----------------|----------|
| x86_64 | linux/amd64 | Intel/AMD 服务器、PC |
| ARM64 | linux/arm64 | 树莓派4/5、Apple M1/M2、AWS Graviton |

## 快速开始

### 方式一：Docker Compose 部署（推荐）

```bash
# 1. 进入项目目录
cd knowledge_base

# 2. 构建并启动 (自动检测当前架构)
docker compose up -d --build

# 3. 查看日志
docker compose logs -f

# 4. 停止服务
docker compose down
```

### 方式二：Docker 命令部署

```bash
# 1. 构建镜像 (当前架构)
docker build -t kb-app:latest .

# 2. 运行容器
docker run -d \
  --name knowledge-base \
  -p 8000:8000 \
  -v kb_data:/app/data \
  -v $(pwd)/models:/app/models:ro \
  --restart unless-stopped \
  kb-app:latest

# 3. 查看日志
docker logs -f knowledge-base
```

### 方式三：多架构构建 + 导出 tar 包

```bash
# 构建脚本支持多种模式
./docker-build.sh              # 多架构构建 (amd64 + arm64)
./docker-build.sh --local      # 仅当前架构
./docker-build.sh --save       # 构建并导出 tar 包
./docker-build.sh --push       # 构建并推送到仓库
```

## 离线部署（目标机器无网络）

### 在有网络的机器上构建

```bash
# 1. 构建镜像并导出为 tar 文件
./docker-build.sh --save

# 2. 同时导出模型文件
tar -czf models.tar.gz models/

# 3. 拷贝到目标机器
scp kb-app-*.tar models.tar.gz user@target-server:~/
```

### 在目标机器上加载

```bash
# 1. 加载 Docker 镜像
docker load -i kb-app-*.tar

# 2. 解压模型文件
tar -xzf models.tar.gz

# 3. 运行容器
docker run -d \
  --name knowledge-base \
  -p 8000:8000 \
  -v kb_data:/app/data \
  -v $(pwd)/models:/app/models:ro \
  --restart unless-stopped \
  kb-app:latest
```

## 多架构构建（同时支持 x86 和 ARM）

### 前提条件

```bash
# 启用 Docker buildx
docker buildx create --name multiarch --use
docker buildx inspect --bootstrap
```

### 构建多架构镜像

```bash
# 构建并同时支持 x86_64 和 ARM64
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t kb-app:latest \
  --load \
  .
```

### 推送到镜像仓库

```bash
# 登录镜像仓库
docker login registry.example.com

# 构建并推送
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/kb-app:latest \
  --push \
  .
```

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| MODEL_DEVICE | cpu | 推理设备: cpu / cuda / auto |
| MODEL_LOCAL_PATH | models/BAAI_bge-small-zh-v1.5 | 嵌入模型路径 |
| RERANKER_LOCAL_PATH | models/BAAI_bge-reranker-base | 重排模型路径 |
| MCP_API_KEY | kb-mcp-secret-key-2024 | MCP 接口密钥 |
| CHUNK_SIZE | 500 | 文本切片大小 |
| CHUNK_OVERLAP | 50 | 切片重叠字符数 |

### 数据持久化

| 容器路径 | 说明 | 挂载方式 |
|---------|------|---------|
| /app/data | 所有数据(知识库、上传、日志) | Docker Volume |
| /app/models | AI 模型文件 | Bind Mount (只读) |

### 资源需求

| 资源 | 最低 | 推荐 |
|------|------|------|
| CPU | 2 核 | 4 核+ |
| 内存 | 1 GB | 4 GB |
| 磁盘 | 2 GB | 10 GB+ |
| 模型 | 500 MB | 1 GB |

## 常用运维命令

```bash
# 查看容器状态
docker ps | grep knowledge-base

# 查看实时日志
docker logs -f knowledge-base

# 进入容器调试
docker exec -it knowledge-base bash

# 重启服务
docker restart knowledge-base

# 更新镜像
docker compose pull && docker compose up -d

# 查看资源使用
docker stats knowledge-base

# 清理旧镜像
docker image prune -f
```

## 访问地址

| 服务 | 地址 |
|------|------|
| Web 管理界面 | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/api/health |
| MCP 服务 | http://localhost:8000/mcp |
