"""全流程功能测试脚本 - 边端侧算力建设指导规范"""
import urllib.request
import urllib.parse
import json
import os
import io
import time
import sys

BASE_URL = "http://localhost:8000"
API_KEY = "kb-mcp-secret-key-2024"
KB_NAME = "边端侧算力规范"
TEST_FILE = "0526_边端侧算力建设指导规范要求-模板v5.docx"

results = {"pass": 0, "fail": 0, "details": []}

def log(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results["pass" if ok else "fail"] += 1
    results["details"].append({"name": name, "status": status, "detail": detail})
    print(f"[{status}] {name}")
    if detail:
        print(f"       {detail}")

def api_get(path, headers=None):
    req = urllib.request.Request(f"{BASE_URL}{path}", headers=headers or {})
    r = urllib.request.urlopen(req)
    return json.loads(r.read())

def api_post(path, data, headers=None):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    body = json.dumps(data).encode() if isinstance(data, dict) else data
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=h, method="POST")
    r = urllib.request.urlopen(req)
    return json.loads(r.read())

print("=" * 70)
print("  全流程功能测试 - 边端侧算力建设指导规范")
print("=" * 70)

# ========== 1. 健康检查 ==========
print("\n--- 1. 健康检查 ---")
try:
    r = api_get("/api/health")
    log("系统健康检查", r["status"] == "healthy", f"status={r['status']}")
except Exception as e:
    log("系统健康检查", False, str(e))

try:
    r = api_get("/api/monitor/status")
    d = r["data"]
    log("系统监控", d["qdrant_status"] == "connected", f"qdrant={d['qdrant_status']}, kbs={d['total_kbs']}")
except Exception as e:
    log("系统监控", False, str(e))

try:
    r = api_get("/api/mcp/health")
    d = r["data"]
    model_ok = d["embedding_model"]["initialized"] and not d["embedding_model"]["demo_mode"]
    log("MCP健康检查", d["status"] == "healthy" and model_ok,
        f"model={d['embedding_model']['model_name']}, dim={d['embedding_model']['embedding_dim']}, demo={d['embedding_model']['demo_mode']}")
except Exception as e:
    log("MCP健康检查", False, str(e))

# ========== 2. 创建知识库 ==========
print("\n--- 2. 创建知识库 ---")
try:
    r = api_post("/api/kb", {"name": KB_NAME, "description": "边端侧算力建设指导规范要求测试知识库"})
    log("创建知识库", r["data"]["success"], r["data"]["message"])
except urllib.error.HTTPError as e:
    err = json.loads(e.read())
    if "已存在" in str(err) or "already exists" in str(err):
        log("创建知识库", True, "知识库已存在，跳过创建")
    else:
        log("创建知识库", False, str(err))

try:
    r = api_get("/api/kb")
    kbs = r["data"]
    kb = [k for k in kbs if k["name"] == KB_NAME]
    log("知识库列表验证", len(kb) == 1, f"找到知识库: {kb[0]['name'] if kb else '未找到'}")
except Exception as e:
    log("知识库列表验证", False, str(e))

# ========== 3. 上传文件 ==========
print("\n--- 3. 上传文件 ---")
if not os.path.exists(TEST_FILE):
    log("文件存在性检查", False, f"文件不存在: {TEST_FILE}")
    sys.exit(1)
log("文件存在性检查", True, f"文件大小: {os.path.getsize(TEST_FILE)} bytes")

try:
    boundary = "boundary123456"
    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="kb_name"\r\n\r\n')
    body.write(KB_NAME.encode() + b"\r\n")
    body.write(f"--{boundary}\r\n".encode())
    body.write(f'Content-Disposition: form-data; name="file"; filename="{TEST_FILE}"\r\n'.encode())
    body.write(b"Content-Type: application/octet-stream\r\n\r\n")
    with open(TEST_FILE, "rb") as f:
        body.write(f.read())
    body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{BASE_URL}/api/import/single",
        data=body.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    r = urllib.request.urlopen(req, timeout=120)
    result = json.loads(r.read())
    log("文件上传导入", result.get("code") == 200 or result.get("data", {}).get("success"),
        f"chunks={result.get('data', {}).get('chunks', 'N/A')}, message={result.get('message', '')}")
except Exception as e:
    log("文件上传导入", False, str(e))

# 等待后台处理
print("\n  等待后台处理 (3秒)...")
time.sleep(3)

# ========== 4. 验证知识库状态 ==========
print("\n--- 4. 验证知识库状态 ---")
try:
    r = api_get("/api/kb")
    kbs = r["data"]
    kb = [k for k in kbs if k["name"] == KB_NAME]
    if kb:
        kb = kb[0]
        doc_ok = kb["doc_count"] > 0
        vec_ok = kb["vector_count"] > 0
        log("文档入库验证", doc_ok, f"doc_count={kb['doc_count']}")
        log("向量入库验证", vec_ok, f"vector_count={kb['vector_count']}")
    else:
        log("知识库状态验证", False, "知识库未找到")
except Exception as e:
    log("知识库状态验证", False, str(e))

# 查看文档明细
try:
    kb_encoded = urllib.parse.quote(KB_NAME)
    r = api_get(f"/api/kb/{kb_encoded}/files")
    docs = r.get("data", [])
    log("文档明细查询", len(docs) > 0, f"文档数={len(docs)}, 第一个={docs[0]['file_name'] if docs else 'N/A'}")
    if docs:
        success_docs = [d for d in docs if d.get("import_status") == "success"]
        if success_docs:
            doc = success_docs[0]
            log("文档切片数验证", doc.get("chunk_count", 0) > 0, f"chunk_count={doc.get('chunk_count')}, status={doc.get('import_status')}")
        else:
            log("文档切片数验证", False, f"所有文档状态: {[d.get('import_status') for d in docs]}")
except Exception as e:
    log("文档明细查询", False, str(e))

# ========== 5. MCP 知识检索测试 ==========
print("\n--- 5. MCP 知识检索测试 ---")
queries = [
    "边端侧算力建设的目标是什么",
    "硬件配置要求",
    "安全规范有哪些",
    "网络架构设计",
    "部署方案",
]

for q in queries:
    try:
        r = api_post("/api/mcp/search", {
            "query": q,
            "kb_name": KB_NAME,
            "top_k": 3,
            "score_threshold": 0.0,
        }, headers={"Authorization": f"Bearer {API_KEY}"})
        results_list = r.get("results", [])
        info = r.get("retrieval_info") or {}
        max_score = info.get("max_score", 0)
        log(f"检索: {q}", len(results_list) > 0,
            f"召回={len(results_list)}条, max_score={max_score:.4f}, 耗时={info.get('total_time_ms', 'N/A')}ms")
        if results_list:
            top = results_list[0]
            text_preview = top["text"][:60].replace("\n", " ")
            log(f"  Top1结果", True, f"score={top['score']:.4f}, text={text_preview}...")
    except Exception as e:
        log(f"检索: {q}", False, str(e))

# ========== 6. MCP 全部接口测试 ==========
print("\n--- 6. MCP 全部接口测试 ---")

# 6.1 MCP 知识库列表
try:
    req = urllib.request.Request(
        f"{BASE_URL}/api/mcp/knowledge-bases",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    r = json.loads(urllib.request.urlopen(req).read())
    kbs = r.get("data", [])
    if isinstance(kbs, dict):
        kbs = kbs.get("knowledge_bases", [])
    log("MCP知识库列表", len(kbs) > 0, f"数量={len(kbs)}")
except Exception as e:
    log("MCP知识库列表", False, str(e))

# 6.2 MCP 工具列表
try:
    req = urllib.request.Request(
        f"{BASE_URL}/api/mcp/tools",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    r = json.loads(urllib.request.urlopen(req).read())
    tools = r.get("data", [])
    log("MCP工具列表", len(tools) >= 4, f"工具数={len(tools)}, 名称={[t.get('name') for t in tools]}")
except Exception as e:
    log("MCP工具列表", False, str(e))

# 6.3 MCP 工具调用 - knowledge_search
try:
    r = api_post("/api/mcp/tool/call", {
        "tool_name": "knowledge_search",
        "arguments": {"query": "边端侧算力", "kb_name": KB_NAME, "top_k": 3},
    }, headers={"Authorization": f"Bearer {API_KEY}"})
    has_result = r.get("result") is not None or r.get("data") is not None
    log("MCP工具调用(knowledge_search)", has_result, str(r)[:100])
except Exception as e:
    log("MCP工具调用(knowledge_search)", False, str(e))

# 6.4 MCP 工具调用 - list_knowledge_bases
try:
    r = api_post("/api/mcp/tool/call", {
        "tool_name": "list_knowledge_bases",
        "arguments": {},
    }, headers={"Authorization": f"Bearer {API_KEY}"})
    has_result = r.get("result") is not None or r.get("data") is not None
    log("MCP工具调用(list_knowledge_bases)", has_result, str(r)[:100])
except Exception as e:
    log("MCP工具调用(list_knowledge_bases)", False, str(e))

# 6.5 鉴权失败测试
try:
    req = urllib.request.Request(
        f"{BASE_URL}/api/mcp/knowledge-bases",
        headers={"Authorization": "Bearer wrong-key"},
    )
    urllib.request.urlopen(req)
    log("鉴权失败测试", False, "应该返回401但未返回")
except urllib.error.HTTPError as e:
    log("鉴权失败测试", e.code == 401, f"正确返回401, code={e.code}")
except Exception as e:
    log("鉴权失败测试", False, str(e))

# 6.6 无鉴权测试
try:
    req = urllib.request.Request(f"{BASE_URL}/api/mcp/knowledge-bases")
    urllib.request.urlopen(req)
    log("无鉴权测试", False, "应该返回401但未返回")
except urllib.error.HTTPError as e:
    log("无鉴权测试", e.code == 401, f"正确返回401, code={e.code}")
except Exception as e:
    log("无鉴权测试", False, str(e))

# ========== 7. 异常容错测试 ==========
print("\n--- 7. 异常容错测试 ---")

# 7.1 重复创建知识库
try:
    r = api_post("/api/kb", {"name": KB_NAME, "description": "重复创建测试"})
    log("重复创建知识库容错", False, "应该报错但未报错")
except urllib.error.HTTPError as e:
    log("重复创建知识库容错", e.code in (400, 409), f"正确返回错误, code={e.code}")
except Exception as e:
    log("重复创建知识库容错", False, str(e))

# 7.2 搜索不存在的知识库
try:
    r = api_post("/api/mcp/search", {
        "query": "测试",
        "kb_name": "不存在的知识库xyz",
        "top_k": 3,
    }, headers={"Authorization": f"Bearer {API_KEY}"})
    log("搜索不存在知识库容错", r.get("total", 0) == 0, "返回空结果，未崩溃")
except Exception as e:
    log("搜索不存在知识库容错", False, str(e))

# ========== 测试报告 ==========
print("\n" + "=" * 70)
print("  测试报告汇总")
print("=" * 70)
print(f"\n  总计: {results['pass'] + results['fail']} 项")
print(f"  通过: {results['pass']} 项")
print(f"  失败: {results['fail']} 项")
print(f"  通过率: {results['pass']/(results['pass']+results['fail'])*100:.1f}%")

if results["fail"] > 0:
    print("\n  失败项:")
    for d in results["details"]:
        if d["status"] == "FAIL":
            print(f"    - {d['name']}: {d['detail']}")

print("\n" + "=" * 70)
