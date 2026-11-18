# 로봇 팔과 카메라(USB)를 Windows에서 WSL로 넘겨준다. 매 세션(재부팅/USB 재연결/WSL 재시작 후) 1번 실행.
#
# 사용 (PowerShell을 "관리자 권한으로 실행", Ubuntu 터미널은 미리 하나 열어둘 것):
#   powershell -ExecutionPolicy Bypass -File attach_usb.ps1
#   카메라를 자동으로 못 고르면:  ... -File attach_usb.ps1 -CameraBusId 1-3
#
# 로봇은 USB-시리얼 칩(CH343, 1a86:55d3)으로 자동 인식한다.
# 카메라는 이름에 Innomaker가 들어간 장치를 고른다. 다른 웹캠이면 -CameraBusId로 직접 지정.
param(
    [string]$RobotBusId,
    [string]$CameraBusId
)

if (-not (Get-Command usbipd -ErrorAction SilentlyContinue)) {
    Write-Host "usbipd가 없습니다. 먼저 설치하세요:  winget install usbipd   (설치 후 PowerShell 다시 열기)" -ForegroundColor Red
    exit 1
}

function Get-UsbDevices {
    $devices = @()
    foreach ($line in (usbipd list)) {
        if ($line -match '^\s*(\d+-\d+)\s+([0-9a-fA-F]{4}:[0-9a-fA-F]{4})\s+(.+?)\s{2,}(\S.*?)\s*$') {
            $devices += [pscustomobject]@{ BusId = $Matches[1]; VidPid = $Matches[2].ToLower(); Name = $Matches[3]; State = $Matches[4] }
        }
    }
    return $devices
}

$devices = Get-UsbDevices
Write-Host "연결된 USB 장치:"
$devices | Format-Table -AutoSize | Out-String | Write-Host

if (-not $RobotBusId) {
    # CH343(55d3)를 먼저 찾는다. 이름 'CH34'만 보면 조이스틱(CH340 나노/ESP32, 1a86:7523)까지 잡힘
    $robot = @($devices | Where-Object { $_.VidPid -eq '1a86:55d3' })
    if ($robot.Count -eq 0) {
        $robot = @($devices | Where-Object { $_.Name -match 'CH34' -and $_.VidPid -ne '1a86:7523' })
    }
    if ($robot.Count -ne 1) {
        Write-Host "로봇(USB-SERIAL CH343)을 못 찾았습니다. 전원/USB 케이블 확인 후 다시 실행하거나 -RobotBusId 로 지정하세요." -ForegroundColor Red
        exit 1
    }
    $RobotBusId = $robot[0].BusId
}

if (-not $CameraBusId) {
    $cam = @($devices | Where-Object { $_.Name -match 'Innomaker' })
    if ($cam.Count -ne 1) {
        # 노트북 내장 카메라(예: "1080p FHD Camera")를 잘못 넘기지 않도록 다른 카메라는 자동으로 고르지 않는다
        Write-Host "Innomaker 카메라를 못 찾았습니다. 꽂혀 있는지 확인하거나, 다른 웹캠이면 위 목록의 BUSID를 -CameraBusId 로 지정하세요." -ForegroundColor Red
        exit 1
    }
    $CameraBusId = $cam[0].BusId
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

foreach ($pair in @(@('로봇', $RobotBusId), @('카메라', $CameraBusId))) {
    $label, $busId = $pair
    $dev = $devices | Where-Object { $_.BusId -eq $busId }
    if (-not $dev) {
        Write-Host "$label BUSID $busId 가 목록에 없습니다." -ForegroundColor Red
        exit 1
    }
    if ($dev.State -match 'Attached') {
        Write-Host "[$label] $busId 이미 WSL에 연결됨 ($($dev.Name))" -ForegroundColor Green
        continue
    }
    if ($dev.State -match 'Not shared') {
        # bind는 장치당 최초 1번만 필요 (재부팅해도 유지), 관리자 권한 필요
        if (-not $isAdmin) {
            Write-Host "[$label] 처음 연결하는 장치라 bind가 필요합니다. PowerShell을 '관리자 권한으로 실행'해서 다시 실행하세요." -ForegroundColor Red
            exit 1
        }
        usbipd bind --busid $busId
    }
    usbipd attach --wsl --busid $busId
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[$label] attach 실패. Ubuntu 터미널이 열려 있는지 확인하고, 안 되면 USB를 뽑았다 꽂은 뒤 다시 실행하세요." -ForegroundColor Red
        exit 1
    }
    Write-Host "[$label] $busId -> WSL 연결 완료 ($($dev.Name))" -ForegroundColor Green
}

Write-Host "`n다음: Ubuntu 터미널에서  bash setup_session.sh"
