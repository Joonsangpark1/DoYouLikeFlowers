# 자작 조이스틱(joystick_fw, Arduino/ESP32)의 시리얼 입력을 WSL의 녹화/학습 프로그램으로 보낸다.
# gamepad_sender.ps1 대신 이걸 켜 둘 것 (둘 중 하나만). WSL 쪽 코드는 그대로.
#
# 사용 (일반 PowerShell, 관리자 권한 필요 없음):
#   powershell -ExecutionPolicy Bypass -File serial_sender.ps1              # COM 포트 자동 선택
#   powershell -ExecutionPolicy Bypass -File serial_sender.ps1 -ComPort COM5
#
# 조이스틱 보드는 usbipd로 WSL에 넘기지 말 것 (Windows에 남아 있어야 COM 포트로 보인다).
# 보드에서 0.3초 넘게 입력이 안 오면 "패드 없음"을 보내서 WSL 쪽이 로봇을 멈추게 한다.
param(
    [string]$ComPort,
    [int]$Baud = 115200,
    [int]$Port = 5557,
    [string]$HostName = "127.0.0.1"
)

$NO_PAD = '{"pad":-1}'

function Find-JoystickPort {
    # 로봇 USB-시리얼(CH343, 1a86:55d3)은 제외. 보통 WSL에 넘겨져 있어서 안 보이지만 혹시 몰라서
    $ports = Get-CimInstance Win32_PnPEntity -Filter "Name LIKE '%(COM%'" |
        Where-Object { $_.PNPDeviceID -notmatch 'VID_1A86&PID_55D3' }
    $ports = @($ports | ForEach-Object {
        if ($_.Name -match '\((COM\d+)\)') { [pscustomobject]@{ Com = $Matches[1]; Name = $_.Name } }
    })
    if ($ports.Count -eq 1) { return $ports[0].Com }
    $named = @($ports | Where-Object { $_.Name -match 'Arduino|CH340|CP210|USB-SERIAL|USB Serial|ESP32|JTAG' })
    if ($named.Count -eq 1) { return $named[0].Com }
    if ($ports.Count -eq 0) { Write-Host "COM 포트가 없습니다. 조이스틱 USB를 꽂으세요." -ForegroundColor Yellow }
    else {
        Write-Host "COM 포트가 여러 개라 못 고릅니다. -ComPort 로 지정하세요:" -ForegroundColor Yellow
        $ports | ForEach-Object { Write-Host "  $($_.Com)  $($_.Name)" }
    }
    return $null
}

function Open-Serial {
    $com = if ($ComPort) { $ComPort } else { Find-JoystickPort }
    if (-not $com) { return $null }
    $sp = New-Object System.IO.Ports.SerialPort $com, $Baud
    # DTR/RTS를 끈 채로 열어야 ESP32가 리셋/부트모드로 안 들어감 (Uno는 리셋 없이 바로 이어짐)
    $sp.DtrEnable = $false
    $sp.RtsEnable = $false
    $sp.ReadTimeout = 300
    $sp.NewLine = "`n"
    $sp.Open()
    $sp.DiscardInBuffer()
    Write-Host "[조이스틱] $com 열림" -ForegroundColor Green
    return $sp
}

Write-Host "조이스틱 송신기: 시리얼 -> $HostName`:$Port (Ctrl+C 종료)"
$serial = $null
$lastMsg = ""

while ($true) {
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.NoDelay = $true
        $client.Connect($HostName, $Port)
        $writer = New-Object System.IO.StreamWriter($client.GetStream())
        $writer.AutoFlush = $true
        Write-Host "[연결됨] WSL 프로그램과 연결" -ForegroundColor Green
        while ($true) {
            $line = $NO_PAD
            if (-not $serial -or -not $serial.IsOpen) {
                try { $serial = Open-Serial } catch { Write-Host "[조이스틱] 포트 열기 실패: $($_.Exception.Message)" -ForegroundColor Yellow; $serial = $null }
                if (-not $serial) { $writer.Write($NO_PAD + "`n"); Start-Sleep -Seconds 1; continue }
            }
            try {
                $raw = $serial.ReadLine().Trim()
                if ($raw -like '{"pad"*') { $line = $raw }
                elseif ($raw) { Write-Host "[보드] $raw" -ForegroundColor DarkCyan; continue }
            } catch {
                $ex = $_.Exception
                if ($ex -is [System.TimeoutException] -or $ex.InnerException -is [System.TimeoutException]) {
                    $line = $NO_PAD  # 보드가 멈춤/리셋 중
                } else {
                    # USB가 빠짐 -> 다시 열기 시도
                    Write-Host "[조이스틱] 연결 끊김: $($ex.Message)" -ForegroundColor Yellow
                    try { $serial.Close() } catch {}
                    $serial = $null
                }
            }
            $msg = if ($line -eq $NO_PAD) { "[입력 없음] 조이스틱 USB/전원 확인" } else { "[조이스틱 OK]" }
            if ($msg -ne $lastMsg) {
                Write-Host $msg -ForegroundColor $(if ($msg -eq "[조이스틱 OK]") { "Green" } else { "Yellow" })
                $lastMsg = $msg
            }
            $writer.Write($line + "`n")
        }
    } catch {
        Write-Host "[대기] WSL 프로그램이 아직 안 켜졌거나 종료됨 -> 1초 뒤 다시 연결" -ForegroundColor DarkGray
        $lastMsg = ""
        Start-Sleep -Seconds 1
    } finally {
        if ($client) { $client.Close() }
    }
}
