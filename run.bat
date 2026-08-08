@echo off
chcp 65001 >nul
echo ========================================
echo   知识库管理系统 - 启动脚本
echo ========================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [错误] 未检测到Python环境，请先安装Python 3.11+
    pause
    exit /b 1
)

echo [1/2] 检查并安装依赖...
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo.
echo [2/2] 启动服务...
echo.
echo   Web界面: http://localhost:8000
echo   API文档: http://localhost:8000/docs
echo   MCP服务: http://localhost:8000/api/mcp
echo.

python -m app.main
pause