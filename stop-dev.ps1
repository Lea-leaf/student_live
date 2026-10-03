# ============================================================================
# 校园生活平台 · 停止开发服务
#
# 用法：.\stop-dev.ps1
#
# 说明：只结束占用 5000（Flask）与 5173（Vite）端口的进程，
#       即 start-dev.ps1 启动的那两个服务，不会影响其他程序。
#
# 编码说明：本文件必须保存为「UTF-8 with BOM」，
# 否则 Windows PowerShell 5.1 会按 GBK 解码中文而报"字符串缺少终止符"。
# ============================================================================

[CmdletBinding()]
param(
    [int[]]$Ports = @(5000, 5173)
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Get-PortOwners($port) {
    <#
        取占用指定端口的进程 ID。
        优先用 Get-NetTCPConnection；在受限环境（ConstrainedLanguage / 权限不足）
        下会失败，退回到解析 netstat 输出。
    #>
    $owners = @()
    try {
        $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop
        $owners = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        $owners = @()
    }

    if ($owners.Count -eq 0) {
        try {
            $lines = netstat -ano | Select-String -Pattern ":$port\s" | Select-String -Pattern 'LISTENING'
            foreach ($line in $lines) {
                $parts = ($line.ToString().Trim() -split '\s+')
                $pidText = $parts[-1]
                if ($pidText -match '^\d+$') { $owners += [int]$pidText }
            }
            $owners = @($owners | Select-Object -Unique)
        } catch {
            $owners = @()
        }
    }
    return $owners
}

$stopped = 0

foreach ($port in $Ports) {
    $owners = Get-PortOwners $port
    if (-not $owners -or $owners.Count -eq 0) {
        Write-Host "[跳过] 端口 $port 没有监听进程" -ForegroundColor DarkGray
        continue
    }

    foreach ($owner in $owners) {
        $process = Get-Process -Id $owner -ErrorAction SilentlyContinue
        $name = if ($process) { $process.ProcessName } else { '未知进程' }
        Write-Host "[停止] 端口 $port -> $name (PID $owner)" -ForegroundColor Yellow

        # 先杀子进程（cmd.exe 拉起的 Vite、Flask reloader 等），再杀自身
        try {
            Get-CimInstance Win32_Process -Filter "ParentProcessId=$owner" -ErrorAction SilentlyContinue |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        } catch { }

        Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
        $stopped++
    }
}

Start-Sleep -Seconds 1
Write-Host ''
if ($stopped -gt 0) {
    Write-Host "开发服务已停止（共结束 $stopped 个进程）。" -ForegroundColor Green
} else {
    Write-Host '没有找到正在运行的服务，无需停止。' -ForegroundColor Green
}
