# ============================================================================
# 校园生活平台 · 一键启动开发环境
#
# 用法（在项目根目录执行）：
#     .\start-dev.ps1                 # 初始化（首次需要）+ 同时启动前后端
#     .\start-dev.ps1 -SkipInit       # 跳过初始化，直接启动（日常用这个）
#     .\start-dev.ps1 -BackendOnly    # 只启动后端
#     .\start-dev.ps1 -InitOnly       # 只做初始化，不启动服务
#     .\start-dev.ps1 -InstallDeps    # 强制重新安装依赖
#
# 如果提示"禁止运行脚本"，用这两种方式绕过执行策略：
#     powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
#     或直接双击 启动开发环境.cmd
#
# 编码说明：本文件必须保存为「UTF-8 with BOM」。
# Windows 自带的 PowerShell 5.1 读取无 BOM 的 UTF-8 文件时会按 GBK 解码，
# 中文注释会被拆坏，脚本报"字符串缺少终止符"而无法运行。请勿另存为无 BOM。
# ============================================================================

[CmdletBinding()]
param(
    [switch]$SkipInit,
    [switch]$BackendOnly,
    [switch]$InitOnly,
    [switch]$InstallDeps
)

$ErrorActionPreference = 'Stop'

# 统一控制台为 UTF-8，避免中文日志乱码（个别宿主不支持时忽略）
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
# 子进程（python 脚本）也按 UTF-8 输出，否则在 GBK 控制台下中文会乱码
$env:PYTHONIOENCODING = 'utf-8'

$Root      = $PSScriptRoot
$Backend   = Join-Path $Root 'backend'
$Frontend  = Join-Path $Root 'frontend'
$LogDir    = Join-Path $Root 'logs'
$VenvPy    = Join-Path $Backend '.venv\Scripts\python.exe'
$PipMirror = 'https://pypi.tuna.tsinghua.edu.cn/simple'
$NpmMirror = 'https://registry.npmmirror.com'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "    [OK] $text" -ForegroundColor Green }
function Write-Note($text) { Write-Host "    [!] $text" -ForegroundColor Yellow }
function Write-Fail($text) { Write-Host "    [X] $text" -ForegroundColor Red }


# ---------------------------------------------------------------------------
# 1. 准备虚拟环境
# ---------------------------------------------------------------------------
Write-Step '检查 Python 环境'

function Get-SystemPython {
    <#
        找一个可用的系统 Python（3.10+）。
        优先 PATH 上的 python，其次 py 启动器，最后几个常见安装路径。
    #>
    $candidates = @()
    $onPath = Get-Command python -ErrorAction SilentlyContinue
    if ($onPath) { $candidates += $onPath.Source }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { $candidates += $launcher.Source }
    $candidates += @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe"
    )
    foreach ($exe in $candidates) {
        if (-not (Test-Path $exe)) { continue }
        try {
            & $exe -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $exe }
        } catch { }
    }
    return $null
}

function Test-VenvUsable($venvPython) {
    <#
        虚拟环境是否还能用。
        关键点：venv 的 python.exe 只是个启动器，它依赖 pyvenv.cfg 里记录的
        「基础解释器」还在原处。基础解释器被删除或移动后，venv 会直接报
        No Python at '...' 而无法启动（本项目踩过：DSH 运行时目录被清理）。
    #>
    if (-not (Test-Path $venvPython)) { return $false }
    try {
        & $venvPython -c 'import sys' 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$needRebuild = $false
if (-not (Test-Path $VenvPy)) {
    $needRebuild = $true
} elseif (-not (Test-VenvUsable $VenvPy)) {
    Write-Note '检测到虚拟环境已失效（基础解释器可能被移动或删除），将重建'
    Remove-Item (Join-Path $Backend '.venv') -Recurse -Force -ErrorAction SilentlyContinue
    $needRebuild = $true
} else {
    Write-Ok "Python: $VenvPy"
}

if ($needRebuild) {
    $systemPython = Get-SystemPython
    if (-not $systemPython) {
        throw '未找到可用的 Python（需 3.10+）。请安装 Python 并勾选 Add Python to PATH 后重试。'
    }
    Write-Note "使用系统 Python 创建虚拟环境：$systemPython"
    Push-Location $Backend
    try { & $systemPython -m venv .venv } finally { Pop-Location }
    if (-not (Test-Path $VenvPy)) { throw '虚拟环境创建失败' }
    Write-Ok "Python: $VenvPy（已重建，接下来会安装依赖）"
    $InstallDeps = $true
}


# ---------------------------------------------------------------------------
# 2. 安装后端依赖
# ---------------------------------------------------------------------------
Write-Step '检查后端依赖'

$depsOk = $true
if ($InstallDeps) {
    $depsOk = $false
} else {
    & $VenvPy -c 'import flask, flask_sqlalchemy, flask_migrate, jwt, dotenv' 2>$null
    if ($LASTEXITCODE -ne 0) { $depsOk = $false }
}

if (-not $depsOk) {
    Write-Note '依赖缺失，开始安装（使用清华镜像加速，可能需要几分钟）…'
    # requirements.txt 含中文注释，部分 Windows 环境下 pip 会按 GBK 解码而报
    # UnicodeDecodeError，故强制 UTF-8 模式。
    $env:PYTHONUTF8 = '1'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    & $VenvPy -m pip install --upgrade pip --quiet
    & $VenvPy -m pip install --only-binary=:all: --timeout 25 --retries 3 `
        -i $PipMirror -r (Join-Path $Backend 'requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        throw '后端依赖安装失败，请检查网络，或手动执行：.\.venv\Scripts\python.exe -m pip install -r requirements.txt'
    }
}
Write-Ok '后端依赖就绪'


# ---------------------------------------------------------------------------
# 3. 初始化数据库
# ---------------------------------------------------------------------------
if (-not $SkipInit) {
    Write-Step '初始化数据库（建表 + 模块 + 系统配置 + 演示数据）'
    Push-Location $Backend
    try { & $VenvPy 'scripts\dev_init.py' } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw '数据库初始化失败' }
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
$NpmCmd = 'npm'
if (-not $BackendOnly) {
    Write-Step '检查前端依赖'

    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        $NpmCmd = 'pnpm'
    } elseif (Get-Command npm -ErrorAction SilentlyContinue) {
        $NpmCmd = 'npm'
    } else {
        Write-Fail '未找到 pnpm / npm 命令'
        Write-Host '    请先安装 Node.js 18+（安装后重开终端），或改用 -BackendOnly 只启动后端。' -ForegroundColor Yellow
        Write-Host '    只启动后端仍可用接口自测：http://127.0.0.1:5000/api/v1/common/health' -ForegroundColor Yellow
        exit 1
    }
    Write-Ok "包管理器: $NpmCmd"

    if ((-not (Test-Path (Join-Path $Frontend 'node_modules'))) -or $InstallDeps) {
        Write-Note '正在安装前端依赖…'
        Push-Location $Frontend
        try {
            if ($NpmCmd -eq 'pnpm') {
                & pnpm install
            } else {
                & npm install "--registry=$NpmMirror"
            }
        } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
    }
    Write-Ok '前端依赖就绪'
}


# ---------------------------------------------------------------------------
# 5. 启动服务（后台运行，日志写入 logs\）
# ---------------------------------------------------------------------------
Write-Step '启动后端 Flask（http://127.0.0.1:5000）'

$backendOut = Join-Path $LogDir 'backend.log'
$backendErr = Join-Path $LogDir 'backend.err.log'
$backendProc = Start-Process -FilePath $VenvPy `
    -ArgumentList 'run.py' `
    -WorkingDirectory $Backend `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -WindowStyle Hidden `
    -PassThru
Write-Ok "后端已启动（PID $($backendProc.Id)），日志：$backendOut"

if (-not $BackendOnly) {
    Write-Step '启动前端 Vite（http://127.0.0.1:5173）'

    $frontendOut = Join-Path $LogDir 'frontend.log'
    $frontendErr = Join-Path $LogDir 'frontend.err.log'
    $frontendProc = Start-Process -FilePath 'cmd.exe' `
        -ArgumentList '/c', "$NpmCmd run dev" `
        -WorkingDirectory $Frontend `
        -RedirectStandardOutput $frontendOut `
        -RedirectStandardError $frontendErr `
        -WindowStyle Hidden `
        -PassThru
    Write-Ok "前端已启动（PID $($frontendProc.Id)），日志：$frontendOut"
}

Start-Sleep -Seconds 5


# ---------------------------------------------------------------------------
# 6. 自检并打印结果
# ---------------------------------------------------------------------------
function Test-Port($port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect('127.0.0.1', $port)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

$backendUp = Test-Port 5000
$frontendUp = $false
if (-not $BackendOnly) { $frontendUp = Test-Port 5173 }

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ' 校园生活平台 开发环境已启动' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan

if ($backendUp) {
    Write-Host ' 后端接口：http://127.0.0.1:5000/api/v1/common/health   [已就绪]' -ForegroundColor Green
} else {
    Write-Fail '后端未就绪 —— 请查看 logs\backend.err.log'
}

if (-not $BackendOnly) {
    if ($frontendUp) {
        Write-Host ' 学生端：  http://127.0.0.1:5173/#/                    [已就绪]' -ForegroundColor Green
        Write-Host ' 管理端：  http://127.0.0.1:5173/#/admin/dashboard' -ForegroundColor Green
    } else {
        Write-Fail '前端未就绪 —— 请查看 logs\frontend.err.log'
    }
    Write-Host ''
    Write-Host ' 注意：地址必须带 #（前端是 hash 路由），而且要用 5173 端口；' -ForegroundColor Yellow
    Write-Host '       5000 端口只提供 API，直接打开会返回 404。' -ForegroundColor Yellow
}

Write-Host ''
Write-Host ' 演示账号：admin / admin123（管理员）'
Write-Host '           20210001 / 123456（学生）'
Write-Host ''
Write-Host ' 停止服务：.\stop-dev.ps1' -ForegroundColor Yellow
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''
