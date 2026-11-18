# XInput이 아닌 일반 USB 패드(DirectInput, 예: 저가형 PS 모양 패드)의 축/버튼 배치를 하나씩 눌러서 알아내고
# pad_map.json에 저장한다. gamepad_sender.ps1은 XInput 패드가 없으면 이 파일로 일반 패드를 읽는다.
#
# 사용 (일반 PowerShell 창에서 직접 실행 - 화면 안내를 보면서 눌러야 함):
#   powershell -ExecutionPolicy Bypass -File pad_mapper.ps1
#
# 패드에 ANALOG/MODE 버튼이 있으면 불을 켜 둘 것 (꺼져 있으면 스틱이 -1/0/1로만 나오거나 버튼으로 바뀜).
param(
    [int]$JoyId = 0,
    [string]$Out = (Join-Path $PSScriptRoot "pad_map.json")
)

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class WinJoy {
    [StructLayout(LayoutKind.Sequential)]
    public struct INFOEX { public uint dwSize, dwFlags, X, Y, Z, R, U, V, Buttons, ButtonNumber, POV, Reserved1, Reserved2; }
    [DllImport("winmm.dll")] static extern uint joyGetPosEx(uint id, ref INFOEX p);
    // 축 6개를 -1~1로, 마지막 칸은 버튼 비트. 실패하면 null
    public static double[] Read(uint id) {
        INFOEX j = new INFOEX(); j.dwSize = (uint)Marshal.SizeOf(j); j.dwFlags = 0xFF;
        if (joyGetPosEx(id, ref j) != 0) return null;
        Func<uint, double> n = v => (v - 32767.5) / 32767.5;
        return new double[] { n(j.X), n(j.Y), n(j.Z), n(j.R), n(j.U), n(j.V), j.Buttons };
    }
}
"@

$AXES = "X", "Y", "Z", "R", "U", "V"

function Read-Pad {
    $s = [WinJoy]::Read($JoyId)
    if ($null -eq $s) { throw "패드(id $JoyId)를 못 읽습니다. USB 연결 확인" }
    return $s
}

$base = Read-Pad
Write-Host "패드 읽기 OK. 지금 아무것도 만지지 마세요 (가운데 값 측정)..."
Start-Sleep -Milliseconds 500
$base = Read-Pad
if ([uint32]$base[6] -ne 0) { Write-Host "눌린 버튼이 있습니다 (btn=$($base[6])). 손 떼고 다시 실행하세요." -ForegroundColor Red; exit 1 }

function Wait-Idle {
    while ($true) {
        $s = Read-Pad
        $moved = $false
        for ($i = 0; $i -lt 6; $i++) { if ([math]::Abs($s[$i] - $base[$i]) -gt 0.25) { $moved = $true } }
        if (-not $moved -and [uint32]$s[6] -eq 0) { return }
        Start-Sleep -Milliseconds 20
    }
}

# 스틱: 가장 많이 움직인 축과 방향. 중간값(0.2~0.8)이 지나갔는지로 아날로그 여부 확인
function Map-Stick($prompt) {
    Wait-Idle
    Write-Host "`n>>> $prompt  (천천히 끝까지 민 뒤 놓기)" -ForegroundColor Cyan
    $peak = @(0.0) * 6; $mid = @($false) * 6; $btnSeen = 0
    while ($true) {
        $s = Read-Pad
        for ($i = 0; $i -lt 6; $i++) {
            $d = $s[$i] - $base[$i]
            if ([math]::Abs($d) -gt [math]::Abs($peak[$i])) { $peak[$i] = $d }
            if ([math]::Abs($d) -gt 0.2 -and [math]::Abs($d) -lt 0.8) { $mid[$i] = $true }
        }
        $btnSeen = $btnSeen -bor [uint32]$s[6]
        $best = 0
        for ($i = 1; $i -lt 6; $i++) { if ([math]::Abs($peak[$i]) -gt [math]::Abs($peak[$best])) { $best = $i } }
        $still = $true
        for ($i = 0; $i -lt 6; $i++) { if ([math]::Abs($s[$i] - $base[$i]) -gt 0.25) { $still = $false } }
        if ([math]::Abs($peak[$best]) -gt 0.7 -and $still) { break }
        if ($btnSeen -ne 0 -and [math]::Abs($peak[$best]) -lt 0.3 -and [uint32]$s[6] -eq 0) {
            Write-Host "  축 대신 버튼($btnSeen)이 눌렸습니다 -> ANALOG 모드가 꺼져 있습니다. 불 켜고 다시 실행하세요." -ForegroundColor Red
            exit 1
        }
        Start-Sleep -Milliseconds 10
    }
    $sign = if ($peak[$best] -gt 0) { 1 } else { -1 }
    $analog = if ($mid[$best]) { "아날로그 OK" } else { "중간값 못 봄 (너무 빨리 밀었거나 디지털)" }
    Write-Host ("  -> 축 {0}, 방향 {1:+0;-0}, {2}" -f $AXES[$best], $sign, $analog) -ForegroundColor Green
    return [ordered]@{ axis = $AXES[$best]; sign = $sign; analog_seen = [bool]$mid[$best] }
}

function Map-Button($prompt) {
    Wait-Idle
    Write-Host "`n>>> $prompt" -ForegroundColor Cyan
    while ($true) {
        $s = Read-Pad
        $b = [uint32]$s[6]
        if ($b -ne 0) {
            Start-Sleep -Milliseconds 80  # 동시에 들어오는 비트까지 모으기
            $b = [uint32](Read-Pad)[6]
            if ($b -eq 0) { continue }
            $num = [math]::Log($b, 2)
            if ($num -ne [math]::Floor($num)) { Write-Host "  버튼이 여러 개 눌림 ($b). 하나만 다시 누르세요." -ForegroundColor Yellow; Wait-Idle; continue }
            Write-Host "  -> 버튼 $([int]$num + 1)번 (비트 $b)" -ForegroundColor Green
            return $b
        }
        for ($i = 0; $i -lt 6; $i++) {
            if ([math]::Abs($s[$i] - $base[$i]) -gt 0.7) {
                # L2/R2가 버튼이 아니라 축으로 나오는 패드
                $sign = if ($s[$i] -gt $base[$i]) { 1 } else { -1 }
                Write-Host ("  -> 축 {0} 방향 {1:+0;-0} (트리거가 축으로 나옴)" -f $AXES[$i], $sign) -ForegroundColor Green
                return [ordered]@{ axis = $AXES[$i]; sign = $sign }
            }
        }
        Start-Sleep -Milliseconds 10
    }
}

Write-Host "`n=== 스틱 ===" -ForegroundColor White
$map = [ordered]@{ joy_id = $JoyId; sticks = [ordered]@{}; buttons = [ordered]@{} }
$map.sticks.ly = Map-Stick "왼쪽 스틱을 위로"
$map.sticks.lx = Map-Stick "왼쪽 스틱을 오른쪽으로"
$map.sticks.ry = Map-Stick "오른쪽 스틱을 위로"
$map.sticks.rx = Map-Stick "오른쪽 스틱을 오른쪽으로"

Write-Host "`n=== 버튼 (하나씩 눌렀다 떼기) ===" -ForegroundColor White
$map.buttons.rb = Map-Button "R1 (개입: 누르는 동안 사람이 조종)"
$map.buttons.y = Map-Button "△ / 위쪽 버튼 (보통 1번) (성공)"
$map.buttons.a = Map-Button "× / 아래쪽 버튼 (보통 3번) (실패)"
$map.buttons.x = Map-Button "□ / 왼쪽 버튼 (보통 4번) (다시 찍기)"
$map.buttons.b = Map-Button "○ / 오른쪽 버튼 (보통 2번)"
$map.buttons.start = Map-Button "START (에피소드 시작)"
$map.buttons.back = Map-Button "SELECT"
$map.buttons.lb = Map-Button "L1"
$map.buttons.rt = Map-Button "R2 (그리퍼 닫기)"
$map.buttons.lt = Map-Button "L2 (그리퍼 열기)"
Wait-Idle

# 같은 입력이 두 역할에 잡혔으면 경고
$seen = @{}
foreach ($k in $map.buttons.Keys) {
    $v = $map.buttons[$k] | ConvertTo-Json -Compress
    if ($seen.ContainsKey($v)) { Write-Host "경고: $k 와 $($seen[$v]) 가 같은 입력입니다 ($v)" -ForegroundColor Yellow } else { $seen[$v] = $k }
}

$json = $map | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText($Out, $json, (New-Object Text.UTF8Encoding $false))
Write-Host "`n저장: $Out" -ForegroundColor Green
Write-Host "이제 gamepad_sender.ps1을 켜면 이 매핑으로 보냅니다."
