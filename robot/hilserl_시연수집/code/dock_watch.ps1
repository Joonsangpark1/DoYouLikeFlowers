# 독 감시 (11-22): 독이 끊겼다 다시 붙어서 로봇이 WSL에서 빠지면(usbipd 상태가 Attached가 아님) reconnect.ps1을 자동 실행.
# 독이 하루에 여러 번 리셋돼서 만듦. 녹화 프로그램(record_prior.py)은 다시 실행해야 함.
# 사용: powershell -ExecutionPolicy Bypass -File dock_watch.ps1   (창 열어 두기, Ctrl+C로 끝)
$here = $PSScriptRoot
$miss = 0
Write-Host "독 감시 시작 (3초마다 로봇 연결 확인)"
while ($true) {
    $line = usbipd list | Select-String "1a86:55d3" | Select-Object -First 1
    $ok = $line -and ($line.ToString() -match "Attached")
    if ($ok) { $miss = 0 } else { $miss++ }
    if ($miss -ge 2) {
        if ($line) {
            Write-Host "$(Get-Date -Format HH:mm:ss) 로봇이 WSL에서 빠짐 -> 재연결"
            & powershell -ExecutionPolicy Bypass -File (Join-Path $here "reconnect.ps1")
            Write-Host "$(Get-Date -Format HH:mm:ss) 재연결 끝. 녹화 중이었다면 record_prior.py 다시 실행"
        } elseif ($miss -eq 2) {
            Write-Host "$(Get-Date -Format HH:mm:ss) 독(로봇 USB)이 안 보임. 다시 붙으면 자동 재연결"
        }
        if ($line) { $miss = 0 }
    }
    Start-Sleep 3
}
