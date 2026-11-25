# 꽃꽂이 로봇 노트북 환경을 한 번에 설치한다 (Windows 10/11). 보통 install.bat을 더블클릭하면 이게 실행된다.
#   1) WSL + Ubuntu   2) usbipd (로봇 USB를 WSL로)   3) Windows Python 3.11 + 카메라 송신기 패키지
#   4) WSL 안 설치 (install_wsl.sh: conda, LeRobot 고정 버전, 패키지 버전 고정, 캘리브레이션, 설정)
# 여러 번 실행해도 된다. 처음에 WSL을 새로 깔면 재부팅 → Ubuntu 사용자 만들기 → 이 파일을 다시 실행.
#
# 직접 실행:  powershell -ExecutionPolicy Bypass -File install_windows.ps1 [-HfUser <HF아이디>] [-Server <GPU서버주소>]
param(
    [string]$HfUser = "",
    [string]$Server = "",
    [string]$Distro = "Ubuntu"
)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

# --- 관리자 권한으로 다시 실행 (WSL·usbipd 설치에 필요) ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "관리자 권한으로 다시 실행합니다 (창이 하나 더 뜹니다)..."
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-File', "`"$PSCommandPath`"", '-Distro', $Distro)
    if ($HfUser) { $a += @('-HfUser', $HfUser) }
    if ($Server) { $a += @('-Server', $Server) }
    Start-Process powershell -Verb RunAs -ArgumentList $a
    exit
}

function Step($t) { Write-Host ""; Write-Host "==================== $t ====================" -ForegroundColor Cyan }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") }
$hasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)

Step "1/4 WSL + $Distro"
$distros = @(wsl -l -q 2>$null | ForEach-Object { ($_ -replace "`0", "").Trim() } | Where-Object { $_ })
if ($distros -notcontains $Distro) {
    Write-Host "$Distro 가 없어서 설치합니다."
    wsl --install -d $Distro
    Write-Host ""
    Write-Host "다음 순서로 진행하세요:" -ForegroundColor Yellow
    Write-Host "  1. 컴퓨터 재부팅 (설치 메시지가 재부팅을 요구하면)"
    Write-Host "  2. 시작 메뉴에서 Ubuntu 실행 → 사용자 이름/비밀번호 만들기"
    Write-Host "  3. install.bat 을 다시 실행 (여기서부터 이어서 설치됨)"
    exit
}
Write-Host "  있음: $Distro"

Step "2/4 usbipd (로봇 USB를 WSL로 넘기는 도구)"
if (-not (Get-Command usbipd -ErrorAction SilentlyContinue)) {
    if (-not $hasWinget) { throw "winget이 없습니다. https://github.com/dorssel/usbipd-win/releases 에서 usbipd-win msi를 받아 설치한 뒤 다시 실행하세요." }
    winget install --exact --id dorssel.usbipd-win --accept-source-agreements --accept-package-agreements
    Refresh-Path
}
if (Get-Command usbipd -ErrorAction SilentlyContinue) { Write-Host "  $(usbipd --version)" } else { Write-Host "  설치됨 (새 PowerShell 창부터 usbipd 명령이 보입니다)" }

Step "3/4 Windows Python 3.11 + 카메라 송신기 패키지"
function Find-Python {
    foreach ($c in @('python', 'py')) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $args_ = if ($c -eq 'py') { @('-3') } else { @() }
        try { $v = & $c @args_ -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null } catch { continue }
        if ($v -and [version]$v -ge [version]'3.10') { return ,(@($c) + $args_) }
    }
    return $null
}
$py = Find-Python
if (-not $py) {
    if (-not $hasWinget) { throw "Python 3.11이 없습니다. https://www.python.org 에서 3.11을 설치(PATH 추가 체크)한 뒤 다시 실행하세요." }
    winget install --exact --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    Refresh-Path
    $py = Find-Python
    if (-not $py) { throw "Python 설치 후에도 찾지 못했습니다. PowerShell을 새로 열고 다시 실행하세요." }
}
$pyExe = $py[0]; $pyArgs = @($py | Select-Object -Skip 1)
Write-Host "  Python: $(& $pyExe @pyArgs --version)"
& $pyExe @pyArgs -m pip install --upgrade pip
& $pyExe @pyArgs -m pip install -r (Join-Path $here "requirements-windows.txt")
& $pyExe @pyArgs -c "import cv2, numpy; print('  OK opencv', cv2.__version__, 'numpy', numpy.__version__)"

Step "4/4 WSL 안 설치 (conda, LeRobot, 패키지 고정, 캘리브레이션) - 10~30분"
# C:\a\b -> /mnt/c/a/b (wsl.exe 출력 인코딩 문제를 피하려고 직접 변환)
$wslHere = "/mnt/" + $here.Substring(0, 1).ToLower() + ($here.Substring(2) -replace '\\', '/')
$bashArgs = @("$wslHere/install_wsl.sh")
if ($HfUser) { $bashArgs += @('--hf-user', $HfUser) }
if ($Server) { $bashArgs += @('--server', $Server) }
wsl -d $Distro -- bash @bashArgs
if ($LASTEXITCODE -ne 0) { Write-Host "WSL 설치 중 오류. 위 메시지를 확인하고 install.bat을 다시 실행하세요." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "설치 완료." -ForegroundColor Green
Write-Host "매 세션 시작: robot\setup\start_session.bat (로봇·카메라 연결 + Ubuntu 창 열기)"
Write-Host "자세한 사용법: robot\README.md"
