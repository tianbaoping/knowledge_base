<#
.SYNOPSIS
    Knowledge Base System - Packaging Script
.DESCRIPTION
    Pack the project into a zip file, excluding runtime data and cache.
    Includes OCR models (RapidOCR + PP-OCRv4) for image/PDF recognition.
.EXAMPLE
    .\pack.ps1                  # Pack with model (~200MB)
    .\pack.ps1 -NoModel         # Pack without model (~5MB)
    .\pack.ps1 -NoEnv           # Pack without conda env
#>

param(
    [switch]$NoModel,
    [switch]$NoEnv
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

$timestamp = Get-Date -Format "yyyyMMdd_HHmm"
$packageName = "knowledge_base_deploy_$timestamp"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Knowledge Base System - Pack" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Items to include
$includeItems = @(
    # 核心代码
    "app",
    # 模型和环境
    "models",
    "envs",
    # Python 依赖
    "requirements.txt",
    # 模型下载
    "download_model.py",
    # 部署脚本
    "deploy.ps1",
    "deploy.sh",
    "run.bat",
    # 打包脚本
    "pack.ps1",
    "pack.sh",
    # Docker 部署
    "Dockerfile",
    "docker-compose.yml",
    # MCP 对接文档
    "MCP_SKILL.md",
    # 项目文档
    "README.md",
    "DEPLOY.md",
    # 工具脚本
    "cleanup_stale.py",
    # 测试脚本
    "run_full_test.py",
    "test_api.py",
    # OCR 服务（RapidOCR / ONNX Runtime）
    "ocr_service",
    "test_ocr_service.py",
    # 配置文件
    ".env.example",
    # systemd 服务配置
    "knowledge-base.service"
)

Write-Host "`nPackaging contents:" -ForegroundColor Yellow
foreach ($item in $includeItems) {
    $fullPath = Join-Path $ProjectDir $item
    if (Test-Path $fullPath) {
        if ($NoModel -and $item -eq "models") {
            Write-Host "  [SKIP] $item (no model)" -ForegroundColor DarkGray
            continue
        }
        if ($NoEnv -and $item -eq "envs") {
            Write-Host "  [SKIP] $item (no env)" -ForegroundColor DarkGray
            continue
        }
        Write-Host "  [OK]   $item" -ForegroundColor Green
    } else {
        Write-Host "  [MISS] $item" -ForegroundColor Red
    }
}

# Create temp directory
$tempDir = Join-Path $env:TEMP $packageName
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

# Copy files
foreach ($item in $includeItems) {
    $fullPath = Join-Path $ProjectDir $item
    if (-not (Test-Path $fullPath)) { continue }
    if ($NoModel -and $item -eq "models") { continue }
    if ($NoEnv -and $item -eq "envs") { continue }

    $destPath = Join-Path $tempDir $item
    if ((Get-Item $fullPath) -is [System.IO.DirectoryInfo]) {
        # Use Copy-Item instead of robocopy to avoid exit code issues
        Copy-Item -Path $fullPath -Destination $destPath -Recurse -Force
        # Clean up cache files
        Get-ChildItem -Path $destPath -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Get-ChildItem -Path $destPath -Recurse -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    } else {
        Copy-Item $fullPath $destPath -Force
    }
}

# Create empty data directories
$dataDirs = @("data\uploads", "data\logs", "data\qdrant", "data\ocr_temp")
foreach ($d in $dataDirs) {
    $dirPath = Join-Path $tempDir $d
    New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
    Set-Content -Path (Join-Path $dirPath ".gitkeep") -Value "" -Encoding UTF8
}

# Create zip
$zipPath = Join-Path $ProjectDir "$packageName.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Write-Host "`nCompressing..." -ForegroundColor Yellow
Compress-Archive -Path "$tempDir\*" -DestinationPath $zipPath -CompressionLevel Optimal

# Cleanup temp
Remove-Item $tempDir -Recurse -Force

# Result
$zipSize = (Get-Item $zipPath).Length / 1MB
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Pack Done!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  File: $zipPath" -ForegroundColor White
Write-Host "  Size: $([math]::Round($zipSize, 1)) MB" -ForegroundColor White
Write-Host "`n  Deploy steps:" -ForegroundColor Yellow
Write-Host "  1. Unzip on target machine" -ForegroundColor White
Write-Host "  2. Run: .\deploy.ps1" -ForegroundColor White
Write-Host "  3. Open: http://localhost:8000" -ForegroundColor White
Write-Host "  4. OCR:  http://localhost:8000/api/ocr/status" -ForegroundColor White
Write-Host "  5. WS:    ws://localhost:8000/ws/import-progress" -ForegroundColor White
Write-Host "`n  OCR Features:" -ForegroundColor Yellow
Write-Host "  - 图片 OCR 识别 (jpg/png/bmp/tiff/gif)" -ForegroundColor White
Write-Host "  - 扫描版 PDF 自动 OCR 处理" -ForegroundColor White
Write-Host "  - 实时导入进度 WebSocket 推送" -ForegroundColor White
Write-Host "  - OCR 状态监控面板" -ForegroundColor White
Write-Host ""
