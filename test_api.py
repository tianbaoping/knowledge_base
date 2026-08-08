import urllib.request
import json
import os
import io

BASE_URL = "http://localhost:8000"

def test_health():
    r = urllib.request.urlopen(f"{BASE_URL}/api/health")
    return json.loads(r.read())

def test_create_kb(name, description=""):
    data = json.dumps({"name": name, "description": description}).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/kb", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req)
    return json.loads(r.read())

def test_list_kb():
    r = urllib.request.urlopen(f"{BASE_URL}/api/kb")
    return json.loads(r.read())

def test_upload_file(kb_name, file_path):
    boundary = "boundary123456"
    body = io.BytesIO()

    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="kb_name"\r\n\r\n')
    body.write(kb_name.encode() + b"\r\n")

    filename = os.path.basename(file_path)
    body.write(f"--{boundary}\r\n".encode())
    body.write(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body.write(b"Content-Type: application/octet-stream\r\n\r\n")
    with open(file_path, "rb") as f:
        body.write(f.read())
    body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())

    data = body.getvalue()
    req = urllib.request.Request(f"{BASE_URL}/api/import/single", data=data,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                                 method="POST")
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()}

def test_mcp_search(kb_name, query, api_key, top_k=5, score_threshold=0.3):
    data = json.dumps({
        "kb_name": kb_name,
        "query": query,
        "top_k": top_k,
        "score_threshold": score_threshold,
    }).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/mcp/search", data=data,
                                 headers={
                                     "Content-Type": "application/json",
                                     "Authorization": f"Bearer {api_key}",
                                 },
                                 method="POST")
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()}

def test_mcp_knowledge_bases(api_key):
    req = urllib.request.Request(f"{BASE_URL}/api/mcp/knowledge-bases",
                                 headers={"Authorization": f"Bearer {api_key}"})
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()}

def test_mcp_health():
    r = urllib.request.urlopen(f"{BASE_URL}/api/mcp/health")
    return json.loads(r.read())

def test_mcp_tools(api_key):
    req = urllib.request.Request(f"{BASE_URL}/api/mcp/tools",
                                 headers={"Authorization": f"Bearer {api_key}"})
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()}

def test_mcp_tool_call(api_key, tool_name, arguments):
    data = json.dumps({"tool_name": tool_name, "arguments": arguments}).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/mcp/tool/call", data=data,
                                 headers={
                                     "Content-Type": "application/json",
                                     "Authorization": f"Bearer {api_key}",
                                 },
                                 method="POST")
    try:
        r = urllib.request.urlopen(req)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()}

def test_monitor():
    r = urllib.request.urlopen(f"{BASE_URL}/api/monitor/status")
    return json.loads(r.read())

if __name__ == "__main__":
    API_KEY = "kb-mcp-secret-key-2024"

    print("=" * 60)
    print("知识库管理系统 API 测试")
    print("=" * 60)

    # 1. Health
    print("\n[1] 健康检查")
    print(json.dumps(test_health(), indent=2, ensure_ascii=False))

    # 2. Monitor
    print("\n[2] 系统监控")
    print(json.dumps(test_monitor(), indent=2, ensure_ascii=False))

    # 3. Create KB
    print("\n[3] 创建知识库")
    result = test_create_kb("demo_kb", "演示知识库")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 4. List KBs
    print("\n[4] 知识库列表")
    print(json.dumps(test_list_kb(), indent=2, ensure_ascii=False))

    # 5. Upload file
    print("\n[5] 上传文件")
    test_file = os.path.join("data", "uploads", "test_doc.txt")
    if os.path.exists(test_file):
        result = test_upload_file("demo_kb", test_file)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"测试文件不存在: {test_file}")

    # 6. Wait a bit and check KB status
    import time
    time.sleep(2)
    print("\n[6] 文件导入后的知识库状态")
    print(json.dumps(test_list_kb(), indent=2, ensure_ascii=False))

    # 7. MCP 服务健康检查
    print("\n[7] MCP 服务健康检查")
    print(json.dumps(test_mcp_health(), indent=2, ensure_ascii=False))

    # 8. MCP 知识库列表
    print("\n[8] MCP 知识库列表")
    print(json.dumps(test_mcp_knowledge_bases(API_KEY), indent=2, ensure_ascii=False))

    # 9. MCP 知识检索
    print("\n[9] MCP 知识检索")
    result = test_mcp_search("demo_kb", "公司的考勤制度是什么", API_KEY, top_k=5, score_threshold=0.0)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 10. MCP 工具列表
    print("\n[10] MCP 工具列表")
    print(json.dumps(test_mcp_tools(API_KEY), indent=2, ensure_ascii=False))

    # 11. MCP 工具调用 - 知识检索
    print("\n[11] MCP 工具调用 (knowledge_search)")
    result = test_mcp_tool_call(API_KEY, "knowledge_search", {
        "query": "公司规章制度",
        "kb_name": "demo_kb",
        "top_k": 3,
    })
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 12. MCP 工具调用 - 知识库列表
    print("\n[12] MCP 工具调用 (list_knowledge_bases)")
    result = test_mcp_tool_call(API_KEY, "list_knowledge_bases", {})
    print(json.dumps(result, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("测试完成!")