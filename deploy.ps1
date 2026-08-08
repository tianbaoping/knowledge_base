<#
.SYNOPSIS
    Knowledge Base System - One-Click Deploy Script
.DESCRIPTION
    Auto detect pre-packaged conda env, extract and use directly.
    Falls back to conda create if no packed env found.
    Supports OCR (RapidOCR + PP-OCRv4) for image and scanned PDF recognition.
.EXAMPLE
    .\deploy.ps1              # Full deploy (use packed env or create new)
    .\deploy.ps1 -SkipModel   # Skip model check
    .\deploy.ps1 -StartOnly   # Start service only (already deployed)
    .\deploy.ps1 -RecreateEnv # Force recreate conda env from requirements.txt
#>

param(
    [switch]$SkipModel,
    [switch]$StartOnly,
    [switch]$RecreateEnv,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

function Write-Step($msg) { Write-Host "`n[STEP] $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [X]  $msg" -ForegroundColor Red }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Knowledge Base System - Deploy" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ========== 0. Determine Python executable ==========
$PackedEnvTar = Join-Path $ProjectDir "envs\knowledge_base_env.tar.gz"
$PackedEnvDir = Join-Path $ProjectDir "envs\knowledge_base"
$PackedPython = Join-Path $PackedEnvDir "python.exe"
$UsePackedEnv = $false

if ($StartOnly) {
    # Try packed env first
    if (Test-Path $PackedPython) {
        $UsePackedEnv = $true
        Write-Step "Using pre-packaged environment"
        Write-OK "Found: $PackedPython"
    } else {
        # Try conda
        Write-Step "Start service (conda env)"
        $condaCmd = Get-Command conda -ErrorAction SilentlyContinue
        if ($condaCmd) {
            $condaExe = (Get-Command conda).Source
            $condaDir = Split-Path $condaCmd.Source
            $condaHook = Join-Path $condaDir "condabin\conda-hook.ps1"
            if (Test-Path $condaHook) { & $condaHook }
            else { (& $condaExe "shell.powershell" "hook") | Invoke-Expression }
            conda activate knowledge_base 2>$null
        }
    }

    Write-Step "Starting service..."
    if ($UsePackedEnv) {
        & $PackedPython -m app.main
    } else {
        python -m app.main
    }
    exit 0
}

# ========== 1. Check for pre-packaged environment ==========
if (-not $RecreateEnv -and (Test-Path $PackedEnvTar)) {
    Write-Step "Found pre-packaged conda environment"

    if (Test-Path $PackedPython) {
        Write-OK "Environment already extracted"
        $UsePackedEnv = $true
    } else {
        Write-Step "Extracting environment (first time only)..."
        New-Item -ItemType Directory -Path $PackedEnvDir -Force | Out-Null

        # Extract tar.gz
        & tar -xzf $PackedEnvTar -C $PackedEnvDir 2>&1 | ForEach-Object {
            Write-Host "  $_" -ForegroundColor DarkGray
        }

        if (Test-Path $PackedPython) {
            # Activate the environment scripts
            $activateScript = Join-Path $PackedEnvDir "Scripts\activate.bat"
            if (Test-Path $activateScript) {
                Write-OK "Environment extracted successfully"
            }
            $UsePackedEnv = $true
        } else {
            Write-Err "Environment extraction failed"
            Write-Warn "Falling back to conda create..."
        }
    }

    if ($UsePackedEnv) {
        # Verify key packages
        Write-Step "Verify dependencies..."
        & $PackedPython -c "import fastapi, uvicorn, qdrant_client, sentence_transformers, loguru; print('OK')" 2>&1 | ForEach-Object {
            if ($_ -match "OK") { Write-OK "All dependencies verified" }
            else { Write-Err "$_" }
        }
    }
}

# ========== 2. Fallback: Create conda env ==========
if (-not $UsePackedEnv) {
    Write-Step "Check conda environment..."

    $condaCmd = Get-Command conda -ErrorAction SilentlyContinue
    if (-not $condaCmd) {
        Write-Err "conda not found and no pre-packaged environment available."
        Write-Host "  Options:"
        Write-Host "    1. Install Miniconda: https://docs.conda.io/en/latest/miniconda.html"
        Write-Host "    2. Get a package with pre-packed env (run pack.ps1 on a machine with conda)"
        exit 1
    }

    # Initialize conda for PowerShell
    $condaExe = (Get-Command conda).Source
    $condaDir = Split-Path $condaCmd.Source
    $condaHook = Join-Path $condaDir "condabin\conda-hook.ps1"
    if (Test-Path $condaHook) {
        & $condaHook
    } else {
        (& $condaExe "shell.powershell" "hook") | Invoke-Expression
    }

    Write-OK "conda found: $condaExe"

    $EnvName = "knowledge_base"
    $envExists = (conda env list | Select-String "\b$EnvName\b")

    if ($RecreateEnv -and $envExists) {
        Write-Warn "Removing existing env '$EnvName'..."
        conda env remove -n $EnvName -y
        $envExists = $false
    }

    if ($envExists) {
        Write-Warn "conda env '$EnvName' already exists, skip creation"
    } else {
        Write-Step "Create conda environment: $EnvName ..."
        conda create -n $EnvName python=3.12 -y --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Err "conda env creation failed"
            exit 1
        }
        Write-OK "conda env created: $EnvName"
    }

    conda activate $EnvName
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to activate conda env: $EnvName"
        exit 1
    }
    Write-OK "conda env activated: $EnvName"

    Write-Step "Install dependencies..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet 2>&1 | ForEach-Object {
        if ($_ -match "Successfully installed") { Write-OK "$_" }
        elseif ($_ -match "ERROR") { Write-Err "$_" }
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Err "Dependency install failed"
        Write-Host "  Try mirror: pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple"
        exit 1
    }
    Write-OK "Dependencies installed"
}

# ========== 3. Check model ==========
if (-not $SkipModel) {
    Write-Step "Check embedding model..."

    $modelDir = Join-Path $ProjectDir "models\BAAI_bge-small-zh-v1.5"
    $modelFile = Join-Path $modelDir "model.safetensors"

    if (Test-Path $modelFile) {
        $modelSize = (Get-Item $modelFile).Length / 1MB
        Write-OK "嵌入模型已就绪: $([math]::Round($modelSize, 1))MB"
    } else {
        Write-Warn "嵌入模型不存在, 尝试下载..."
        Write-Host "  Manual download: https://huggingface.co/BAAI/bge-small-zh-v1.5"

        if ($UsePackedEnv) {
            & $PackedPython download_model.py 2>&1 | ForEach-Object { Write-Host "  $_" }
        } else {
            python download_model.py 2>&1 | ForEach-Object { Write-Host "  $_" }
        }

        if (Test-Path $modelFile) {
            Write-OK "嵌入模型下载完成"
        } else {
            Write-Warn "嵌入模型下载失败, 将以演示模式启动 (Mock Embedding)"
            Write-Host "  Put model files in: $modelDir"
        }
    }
} else {
    Write-Step "Skip model check"
}

# ========== 3.5 Check OCR models ==========
Write-Step "Check OCR models..."
$ocrModelDir = Join-Path $ProjectDir "ocr_service\models"
$ocrModels = @(
    "ch_PP-OCRv4_det_infer.onnx",
    "ch_PP-OCRv4_rec_infer.onnx",
    "ch_ppocr_mobile_v2.0_cls_infer.onnx"
)
$ocrReady = $true
$ocrTotalSize = 0

if (-not (Test-Path $ocrModelDir)) {
    Write-Err "OCR 模型目录不存在: $ocrModelDir"
    Write-Host "  OCR 功能将不可用。请确保 ocr_service\models\ 目录包含 3 个 ONNX 模型文件"
    Write-Host "  参考 README.md 中的 OCR 模型部署说明"
    $ocrReady = $false
} else {
    foreach ($modelFile in $ocrModels) {
        $modelPath = Join-Path $ocrModelDir $modelFile
        if (Test-Path $modelPath) {
            $modelSize = [math]::Round((Get-Item $modelPath).Length / 1MB, 1)
            $ocrTotalSize += $modelSize
            Write-OK "$modelFile ($modelSize MB)"
        } else {
            Write-Err "$modelFile [MISSING]"
            $ocrReady = $false
        }
    }

    if ($ocrReady) {
        Write-OK "OCR 模型就绪 (共 3 个文件, ~$ocrTotalSize MB)"
        Write-Host "  引擎: RapidOCR + ONNX Runtime"
        Write-Host "  版本: PP-OCRv4 (中文)"
        Write-Host "  支持: jpg/png/bmp/tiff/gif 图片 + 扫描版 PDF"
    } else {
        Write-Warn "OCR 模型不完整, OCR 功能将不可用"
        Write-Host "  缺失的模型文件需要手动放置到: $ocrModelDir"
        Write-Host "  下载地址: 参考 README.md 或 PaddleOCR 官方仓库"
    }
}

# ========== 4. Init data dirs ==========
Write-Step "Init data directories..."

$dirs = @("data\uploads", "data\logs", "data\qdrant", "data\ocr_temp")
foreach ($d in $dirs) {
    $fullPath = Join-Path $ProjectDir $d
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
    }
}
Write-OK "Data directories ready (uploads, logs, qdrant, ocr_temp)"

# ========== 5. Check port ==========
Write-Step "Check port $Port..."

$portInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($portInUse) {
    $oldPid = $portInUse.OwningProcess
    $oldProc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
    Write-Warn "Port $Port in use (PID: $oldPid, $($oldProc.ProcessName))"
    $choice = Read-Host "  Kill process? (y/n)"
    if ($choice -eq 'y' -or $choice -eq 'Y') {
        Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        Write-OK "Process $oldPid killed"
    } else {
        Write-Err "Port in use, cannot start"
        exit 1
    }
} else {
    Write-OK "Port $Port available"
}

# ========== 6. Start service ==========
Write-Step "Start Knowledge Base System..."
Write-Host ""
Write-Host "  Web UI:  http://localhost:$Port" -ForegroundColor Green
Write-Host "  API Doc: http://localhost:$Port/docs" -ForegroundColor Green
Write-Host "  MCP Server: http://localhost:$Port/mcp  (MCP 2025-11-25)" -ForegroundColor Green
Write-Host "  MCP REST:   http://localhost:$Port/api/mcp (兼容)" -ForegroundColor Green
Write-Host "  MCP Key: kb-mcp-secret-key-2024" -ForegroundColor Green
Write-Host "  OCR Status: http://localhost:$Port/api/ocr/status" -ForegroundColor Green
Write-Host "  Import WS:  ws://localhost:$Port/ws/import-progress" -ForegroundColor Green
if ($UsePackedEnv) {
    Write-Host "  Env:     Pre-packaged (no conda required)" -ForegroundColor DarkGray
} else {
    Write-Host "  Env:     conda ($EnvName)" -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "  Press Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host "----------------------------------------`n"

if ($UsePackedEnv) {
    & $PackedPython -m app.main
} else {
    python -m app.main
}
