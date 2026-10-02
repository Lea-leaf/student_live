# ============================================================================
# 校园生活平台 · 一键启动开发环境（Windows PowerShell）
#
# 用法（在项目根目录执行）：
#     .\start-dev.ps1                # 初始化（如需要）+ 同时启动前后端
#     .\start-dev.ps1 -SkipInit      # 跳过初始化，直接启动
#     .\start-dev.ps1 -BackendOnly   # 只启动后端
#     .\start-dev.ps1 -InitOnly      # 只做初始化，不启动服务
#
# 脚本做四件事：
#   1. 检查 Python / Node 与依赖是否就绪（缺失则自动安装）；
#   2. 初始化数据库（建表 + 模块 + 配置 + 演示数据）；
#   3. 后台启动 Flask（5000）与 Vite（5173），日志写入 logs\ 目录；
#   4. 打印访问地址与演示账号。
# ============================================================================

[CmdletBinding()]
param(
    [switch]$SkipInit,
    [switch]$BackendOnly,
    [switch]$InitOnly
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-Ok($text) { Write-Host "    [OK] $text" -ForegroundColor Green }
function Write-Warn2($text) { Write-Host "    [!] $text" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# 1. 定位 Python
# ---------------------------------------------------------------------------
Write-Step '检查 Python 环境'
$VenvPython = Join-Path $Backend '.venv\Scripts\python.exe'

if (-not (Test-Path $VenvPython)) {
    $systemPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $systemPython) {
        throw '未找到 python，请先安装 Python 3.10+ 并加入 PATH'
    }
    Write-Warn2 "未发现虚拟环境，正在创建：$VenvPython"
    Push-Location $Backend
    & $systemPython -m venv .venv
    Pop-Location
}
Write-Ok "Python: $VenvPython"

# ---------------------------------------------------------------------------
# 2. 安装后端依赖
# ---------------------------------------------------------------------------
Write-Step '检查后端依赖'
& $VenvPython -c 'import flask, flask_sqlalchemy, jwt, flask_migrate' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 '依赖缺失，开始安装（使用清华镜像加速）…'
    & $VenvPython -m pip install --upgrade pip --quiet
    & $VenvPython -m pip install --only-binary=:all: `
        -i https://pypi.tuna.tsinghua.edu.cn/simple `
        -r (Join-Path $Backend 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw '后端依赖安装失败' }
}
Write-Ok '后端依赖就绪'

# ---------------------------------------------------------------------------
# 3. 初始化数据库
# ---------------------------------------------------------------------------
if (-not $SkipInit) {
    Write-Step '初始化数据库（建表 + 模块 + 配置 + 演示数据）'
    Push-Location $Backend
    & $VenvPython 'scripts\dev_init.py'
    Pop-Location
    Write-Ok '数据库初始化完成'
} else {
    Write-Ok '跳过初始化（-SkipInit）'
}

if ($InitOnly) {
    Write-Host "`n初始化完成。启动服务请执行：.\start-dev.ps1 -SkipInit" -ForegroundColor Cyan
    exit 0
}

# ---------------------------------------------------------------------------
# 4. 安装前端依赖
# ---------------------------------------------------------------------------
if (-not $BackendOnly) {
    Write-Step '检查前端依赖'
    $NodeModules = Join-Path $Frontend 'node_modules'
    if (-not (Test-Path $NodeModules)) {
        Push-Location $Frontend
        if (Get-Command pnpm -ErrorAction SilentlyContinue) {
            pnpm install
        } else {
            npm install --registry=https://registry.npmmirror.com
        }
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
        Pop-Location
    }
    Write-Ok '前端依赖就绪'
}

# ---------------------------------------------------------------------------
# 5. 启动服务
# ---------------------------------------------------------------------------
Write-Step '启动后端 Flask（http://127.0.0.1:5000）'
$backendLog = Join-Path $LogDir 'backend.log'
$backendErr = Join-Path $LogDir 'backend.err.log'
Start-Process -FilePath $VenvPython `
    -ArgumentList 'run.py' `
    -WorkingDirectory $Backend `
    -RedirectStandardOutput $backendLog `
    -RedirectStandardError $backendErr `
    -WindowStyle Hidden
Write-Ok "后端日志：$backendLog"

if (-not $BackendOnly) {
    Write-Step '启动前端 Vite（http://127.0.0.1:5173）'
    $frontendLog = Join-Path $LogDir 'frontend.log'
    $frontendErr = Join-Path $LogDir 'frontend.err.log'
    $npmCmd = if (Get-Command pnpm -ErrorAction SilentlyContinue) { 'pnpm' } else { 'npm' }
    Start-Process -FilePath 'cmd.exe' `
        -ArgumentList '/c', "$npmCmd run dev" `
        -WorkingDirectory $Frontend `
        -RedirectStandardOutput $frontendLog `
        -RedirectStandardError $frontendErr `
        -WindowStyle Hidden
    Write-Ok "前端日志：$frontendLog"
}

Start-Sleep -Seconds 4

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host " 校园生活平台 开发环境已启动" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " 学生端：  http://127.0.0.1:5173/#/"
if (-not $BackendOnly) {
    Write-Host " 管理端：  http://127.0.0.1:5173/#/admin/dashboard"
}
Write-Host " 后端接口：http://127.0.0.1:5000/api/v1/common/health"
Write-Host ""
Write-Host " 演示账号：admin / admin123（管理员）"
Write-Host "           20210001 / 123456（学生）"
Write-Host ""
Write-Host " 停止服务：.\stop-dev.ps1" -ForegroundColor Yellow
Write-Host "============================================================`n" -ForegroundColor Cyan
