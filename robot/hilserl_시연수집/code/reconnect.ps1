# 독이 끊겼다 다시 붙어서 busid가 바뀌었을 때 한 번에 복구 (11-22)
#   1. 로봇(CH343 1a86:55d3)을 지금 busid로 WSL에 다시 attach (자동 재연결)
#   2. 손목 카메라(5558)·C270(5559)·게임패드(5557) 송신기 다시 시작
# 사용: powershell -ExecutionPolicy Bypass -File reconnect.ps1
$ErrorActionPreference = "Continue"
$here = $PSScriptRoot


$line = usbipd list | Select-String "1a86:55d3" | Select-Object -First 1
if (-not $line) { Write-Host "로봇 USB(CH343)가 안 보임. 케이블/독 확인"; exit 1 }
# 장치 확인 뒤에 기존 연결·송신기 정리 (로봇이 없으면 아무것도 안 끔)
Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match 'usbipd.*attach|usbip-auto-attach|camera_sender_windows|gamepad_sender'
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 1
$busid = ($line.ToString().Trim() -split '\s+')[0]
Write-Host "로봇 busid $busid"
usbipd bind --busid $busid 2>$null
Start-Process usbipd -WindowStyle Minimized -ArgumentList 'attach', '--wsl', '--busid', $busid, '--auto-attach'
Start-Sleep 5  # 독이 막 붙은 직후엔 카메라가 아직 안 열려서 송신기가 실패함 (11-22)

Start-Process powershell -WindowStyle Minimized -WorkingDirectory $here -ArgumentList '-NoExit', '-Command', 'python camera_sender_windows.py --find innomaker'
Start-Process powershell -WindowStyle Minimized -WorkingDirectory $here -ArgumentList '-NoExit', '-Command', 'python camera_sender_windows.py --find c270 --port 5559 --exposure -5'
Start-Process powershell -WindowStyle Minimized -WorkingDirectory $here -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', 'gamepad_sender.ps1'

Start-Sleep 6
$dev = wsl -d Ubuntu -- bash -lc "ls /dev/serial/by-id/ 2>/dev/null"
if ($dev) { Write-Host "WSL 로봇 포트 OK: $dev" } else { Write-Host "WSL에 로봇 포트가 아직 없음 (몇 초 뒤 다시 확인)" }
Write-Host "게임패드 ANALOG 불(빨간색) 켜져 있는지 확인"
