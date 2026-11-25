# 매 세션(노트북 재부팅·USB 다시 꽂음·독 재연결 뒤) 시작할 때 1번: 로봇·카메라·게임패드를 WSL로 연결하고 Ubuntu 창을 연다.
#   smolvla 모드(기본): 로봇 + 손목 카메라          → Ubuntu 창에서 smolvla_데이터수집/code/setup_session.sh
#   hil 모드          : 로봇 + 손목 카메라 + C270 + 게임패드 → hilserl_시연수집/code/setup_session.sh
# 사용: start_session.bat            또는  powershell -ExecutionPolicy Bypass -File start_session.ps1 -Mode hil
param(
    [ValidateSet("smolvla", "hil")][string]$Mode = "smolvla",
    [string]$WristCam = "innomaker",   # 손목 카메라 이름 일부 (camera_sender_windows.py --find)
    [string]$FixedCam = "c270",        # hil 모드 고정 카메라 이름 일부
    [string]$Distro = "Ubuntu"
)
$ErrorActionPreference = "Continue"
$robotDir = Split-Path $PSScriptRoot -Parent
$code = if ($Mode -eq "hil") { Join-Path $robotDir "hilserl_시연수집\code" } else { Join-Path $robotDir "smolvla_데이터수집\code" }
$senderDir = Join-Path $robotDir "hilserl_시연수집\code"   # 카메라·게임패드 송신기 (두 폴더 내용 같음)

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Start-Process powershell -Verb RunAs -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Mode', $Mode, '-WristCam', $WristCam, '-FixedCam', $FixedCam, '-Distro', $Distro)
    exit
}
if (-not (Get-Command usbipd -ErrorAction SilentlyContinue)) { Write-Host "usbipd가 없습니다. install.bat 먼저" -ForegroundColor Red; Read-Host "Enter"; exit 1 }

# WSL을 먼저 깨워 둔다 (꺼져 있으면 attach 실패)
wsl -d $Distro -- true

Write-Host "== 1. 로봇 USB (CH343 1a86:55d3) → WSL"
$line = usbipd list | Select-String "1a86:55d3" | Select-Object -First 1
if (-not $line) { Write-Host "  로봇이 안 보입니다. 전원·USB 케이블·독 확인 후 다시 실행" -ForegroundColor Red; Read-Host "Enter"; exit 1 }
# 이전 세션의 송신기·attach 정리
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'usbipd.*attach|camera_sender_windows|gamepad_sender' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep 1
$busid = ($line.ToString().Trim() -split '\s+')[0]
usbipd bind --busid $busid 2>$null
Start-Process usbipd -WindowStyle Minimized -ArgumentList 'attach', '--wsl', '--busid', $busid, '--auto-attach'
Write-Host "  busid $busid 연결 (끊겨도 자동 재연결 창이 최소화돼 있음)"
Start-Sleep 4

Write-Host "== 2. 카메라 송신기 (Windows에서 찍어서 WSL로 보냄)"
Start-Process powershell -WindowStyle Minimized -WorkingDirectory $senderDir -ArgumentList '-NoExit', '-Command', "python camera_sender_windows.py --find $WristCam"
Write-Host "  손목 카메라 '$WristCam' → 5558"
if ($Mode -eq "hil") {
    Start-Process powershell -WindowStyle Minimized -WorkingDirectory $senderDir -ArgumentList '-NoExit', '-Command', "python camera_sender_windows.py --find $FixedCam --port 5559 --exposure -5"
    Write-Host "  고정 카메라 '$FixedCam' → 5559"
    Write-Host "== 3. 게임패드 송신기 → 5557 (일반 패드는 처음 한 번 pad_mapper.ps1)"
    Start-Process powershell -WindowStyle Minimized -WorkingDirectory $senderDir -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', 'gamepad_sender.ps1'
    Write-Host "  게임패드 ANALOG 불(빨간색)이 켜져 있는지 확인" -ForegroundColor Yellow
}

Write-Host "== Ubuntu 창 열기 → setup_session.sh (장치 권한·캘리브레이션 점검)"
$wslCode = "/mnt/" + $code.Substring(0, 1).ToLower() + ($code.Substring(2) -replace '\\', '/')
Start-Process wsl -ArgumentList @('-d', $Distro, '--cd', $wslCode, '--', 'bash', '-ic', 'bash setup_session.sh; exec bash')
Write-Host ""
Write-Host "완료. 송신기 창(최소화)은 녹화 끝날 때까지 닫지 마세요." -ForegroundColor Green
Start-Sleep 3
