# ============================================================================
# 校园生活平台 · 停止开发服务
#
# 用法：.\stop-dev.ps1
#
# 说明：只结束占用 5000（Flask）与 5173（Vite）端口的进程，
#       即 start-dev.ps1 启动的那两个服务，不会影响其他程序。
# ============================================================================

[CmdletBinding()]
param(
    [int[]]$Ports = @(5000, 5173)
)

$ErrorActionPreference = 'Continue'

foreach ($port in $Ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        Write-Host "[跳过] 端口 $port 没有监听进程" -ForegroundColor DarkGray
        continue
    }
    foreach ($owner in ($connections | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $process = Get-Process -Id $owner -ErrorAction SilentlyContinue
        if (-not $process) { continue }
        Write-Host "[停止] 端口 $port -> $($process.ProcessName) (PID $owner)" -ForegroundColor Yellow
        Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Seconds 1
Write-Host "`n开发服务已停止。" -ForegroundColor Green
