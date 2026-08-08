@echo off
chcp 65001 >nul
REM ============================================
REM PaddleOCR 服务启动脚本 (Windows)
REM ============================================

set OCR_HOST=0.0.0.0
set OCR_PORT=8002
REM set OCR_USE_GPU=true

echo ========================================
echo   PaddleOCR Service Starting...
echo ========================================
echo   Host: %OCR_HOST%
echo   Port: %OCR_PORT%
echo   GPU:  %OCR_USE_GPU%
echo ========================================
echo.

python -m ocr_service.main

pause
