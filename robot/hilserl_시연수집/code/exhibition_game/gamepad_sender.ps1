# 게임패드 입력을 Windows에서 읽어서 WSL의 녹화 프로그램으로 보낸다. 녹화하는 동안 이 창을 켜 둘 것.
#
# 사용 (일반 PowerShell, 관리자 권한 필요 없음):
#   powershell -ExecutionPolicy Bypass -File gamepad_sender.ps1
#   포트를 바꿨으면:  ... -File gamepad_sender.ps1 -Port 5557
#
# 왜 Windows에서 읽나: WSL 커널에는 Xbox 패드 드라이버가 없어서 usbipd로 넘겨도 패드가 안 보인다.
# Windows 기본 내장 XInput(xinput1_4.dll)으로 읽으므로 설치할 것이 없다.
# XInput = Xbox 호환 패드. 스위치/플스 패드는 X-input 모드로 바꾸거나 Xbox 호환 패드를 쓸 것.
#
# WSL 프로그램(gamepad_test.py / record_demos.py)이 아직 안 켜져 있어도 된다. 켜질 때까지 1초마다 다시 연결한다.
param(
    [int]$Port = 5567,
    [string]$HostName = "127.0.0.1",
    [int]$Hz = 60
)

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class XInputPad {
    [StructLayout(LayoutKind.Sequential)]
    public struct GAMEPAD {
        public ushort wButtons;
        public byte bLeftTrigger;
        public byte bRightTrigger;
        public short sThumbLX;
        public short sThumbLY;
        public short sThumbRX;
        public short sThumbRY;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct STATE {
        public uint dwPacketNumber;
        public GAMEPAD Gamepad;
    }

    [DllImport("xinput1_4.dll")]
    private static extern uint XInputGetState(uint dwUserIndex, out STATE pState);

    static string F(double v) { return v.ToString("0.000", System.Globalization.CultureInfo.InvariantCulture); }

    // 연결된 첫 번째 패드 상태를 JSON 한 줄로. 패드가 없으면 pad=-1
    public static string Read() {
        for (uint i = 0; i < 4; i++) {
            STATE s;
            if (XInputGetState(i, out s) == 0) {
                GAMEPAD g = s.Gamepad;
                return "{\"pad\":" + i +
                    ",\"lx\":" + F(g.sThumbLX / 32768.0) + ",\"ly\":" + F(g.sThumbLY / 32768.0) +
                    ",\"rx\":" + F(g.sThumbRX / 32768.0) + ",\"ry\":" + F(g.sThumbRY / 32768.0) +
                    ",\"lt\":" + F(g.bLeftTrigger / 255.0) + ",\"rt\":" + F(g.bRightTrigger / 255.0) +
                    ",\"btn\":" + g.wButtons + "}";
            }
        }
        return "{\"pad\":-1}";
    }
}

// XInput이 아닌 일반 USB 패드 (winmm). 축 6개 -1~1 + 마지막 칸 버튼 비트, 실패하면 null
public static class WinJoy {
    [StructLayout(LayoutKind.Sequential)]
    public struct INFOEX { public uint dwSize, dwFlags, X, Y, Z, R, U, V, Buttons, ButtonNumber, POV, Reserved1, Reserved2; }
    [DllImport("winmm.dll")] static extern uint joyGetPosEx(uint id, ref INFOEX p);
    public static double[] Read(uint id) {
        INFOEX j = new INFOEX(); j.dwSize = (uint)Marshal.SizeOf(j); j.dwFlags = 0xFF;
        if (joyGetPosEx(id, ref j) != 0) return null;
        Func<uint, double> n = v => (v - 32767.5) / 32767.5;
        return new double[] { n(j.X), n(j.Y), n(j.Z), n(j.R), n(j.U), n(j.V), j.Buttons };
    }
}
"@

# 일반 USB 패드용 매핑 (pad_mapper.ps1로 만듦). 없으면 XInput 패드만 씀
$MapPath = Join-Path $PSScriptRoot "pad_map.json"
$PadMap = if (Test-Path $MapPath) { Get-Content $MapPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
$AXIS_INDEX = @{ X = 0; Y = 1; Z = 2; R = 3; U = 4; V = 5 }
$XINPUT_BIT = @{ start = 0x0010; back = 0x0020; lb = 0x0100; rb = 0x0200; a = 0x1000; b = 0x2000; x = 0x4000; y = 0x8000 }

function F([double]$v) { $v.ToString("0.000", [Globalization.CultureInfo]::InvariantCulture) }

# 매핑 하나(버튼 비트 숫자 또는 {axis, sign})가 눌렸는지 0~1로
function Get-Pressed($m, $s) {
    if ($null -eq $m) { return 0.0 }
    if ($null -ne $m.axis) { return [math]::Max(0.0, $m.sign * $s[$AXIS_INDEX[$m.axis]]) }
    if (([uint32]$s[6] -band [uint32]$m) -ne 0) { return 1.0 } else { return 0.0 }
}

# 일반 패드 상태를 XInput과 같은 JSON으로 (위 = +, 오른쪽 = +, 버튼은 XInput 비트)
function Read-MappedPad {
    $s = [WinJoy]::Read([uint32]$PadMap.joy_id)
    if ($null -eq $s) { return '{"pad":-1}' }
    $ax = @{}
    foreach ($k in "lx", "ly", "rx", "ry") {
        $m = $PadMap.sticks.$k
        $ax[$k] = [math]::Max(-1.0, [math]::Min(1.0, $m.sign * $s[$AXIS_INDEX[$m.axis]]))
    }
    $btn = 0
    foreach ($k in $XINPUT_BIT.Keys) {
        if ((Get-Pressed $PadMap.buttons.$k $s) -gt 0.5) { $btn = $btn -bor $XINPUT_BIT[$k] }
    }
    $lt = Get-Pressed $PadMap.buttons.lt $s
    $rt = Get-Pressed $PadMap.buttons.rt $s
    return "{`"pad`":0,`"lx`":$(F $ax.lx),`"ly`":$(F $ax.ly),`"rx`":$(F $ax.rx),`"ry`":$(F $ax.ry),`"lt`":$(F $lt),`"rt`":$(F $rt),`"btn`":$btn}"
}

function Read-AnyPad {
    if ($PadMap) { return (Read-MappedPad) }
    return '{"pad":-1}'
}
if ($PadMap) { Write-Host "일반 USB 패드 매핑 사용: $MapPath (전시용: 이 매핑만 사용)" }

$interval = [int](1000 / $Hz)
Write-Host "게임패드 송신기: $HostName`:$Port 로 보냄 (Ctrl+C 종료)"
$lastPadMsg = ""

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
            $line = Read-AnyPad
            $padMsg = if ($line -like '*"pad":-1*') { "[패드 없음] 게임패드를 연결하거나 켜세요 (Xbox 호환/X-input 모드, 일반 USB 패드는 pad_mapper.ps1 먼저)" } else { "[패드 OK]" }
            if ($padMsg -ne $lastPadMsg) {
                Write-Host $padMsg -ForegroundColor $(if ($padMsg -eq "[패드 OK]") { "Green" } else { "Yellow" })
                $lastPadMsg = $padMsg
            }
            $writer.Write($line + "`n")
            Start-Sleep -Milliseconds $interval
        }
    } catch {
        Write-Host "[대기] WSL 프로그램이 아직 안 켜졌거나 종료됨 -> 1초 뒤 다시 연결" -ForegroundColor DarkGray
        $lastPadMsg = ""
        Start-Sleep -Seconds 1
    } finally {
        if ($client) { $client.Close() }
    }
}
