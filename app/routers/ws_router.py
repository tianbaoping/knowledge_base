"""
导入进度 WebSocket 路由

提供实时导入进度推送
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.import_task_manager import import_task_manager

router = APIRouter(tags=["导入进度"])


@router.websocket("/ws/import-progress")
async def websocket_import_progress(websocket: WebSocket):
    """WebSocket 端点 - 推送导入进度"""
    await import_task_manager.register_websocket(websocket)

    try:
        while True:
            # 保持连接，客户端可以发送消息（如请求历史任务）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            elif data.startswith("get_task:"):
                task_id = data.split(":", 1)[1]
                task = import_task_manager.get_task(task_id)
                if task:
                    await websocket.send_json({
                        "type": "task_detail",
                        "data": task.to_dict(),
                    })
            elif data == "get_all":
                await websocket.send_json({
                    "type": "all_tasks",
                    "data": import_task_manager.get_all_tasks(),
                })
    except WebSocketDisconnect:
        pass
    finally:
        await import_task_manager.unregister_websocket(websocket)


@router.get("/api/import-tasks")
async def get_import_tasks():
    """获取所有导入任务"""
    return {
        "success": True,
        "data": import_task_manager.get_all_tasks(),
    }


@router.get("/api/import-tasks/active")
async def get_active_import_tasks():
    """获取活跃的导入任务"""
    return {
        "success": True,
        "data": import_task_manager.get_active_tasks(),
    }


@router.get("/api/import-tasks/{task_id}")
async def get_import_task(task_id: str):
    """获取单个导入任务详情"""
    task = import_task_manager.get_task(task_id)
    if not task:
        return {"success": False, "message": "任务不存在"}
    return {
        "success": True,
        "data": task.to_dict(),
    }
