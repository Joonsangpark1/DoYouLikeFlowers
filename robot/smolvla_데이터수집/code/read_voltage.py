"""모터 6개의 공급 전압(Present_Voltage, 0.1 V 단위) 읽기. 6.6 V 아래면 배터리 충전/교체.

lerobot 없이 scservo_sdk만 씀 (녹화 프로그램이 포트를 잡고 있으면 먼저 끌 것).
사용: python read_voltage.py [/dev/ttyACM0]
"""

import sys

import scservo_sdk as scs

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
ADDR_VOLTAGE, ADDR_TEMP, ADDR_LOAD = 62, 63, 60
NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]

port = scs.PortHandler(PORT)
ph = scs.PacketHandler(0)
if not port.openPort() or not port.setBaudRate(1_000_000):
    sys.exit(f"포트 {PORT} 열기 실패")
vs = []
for i, n in enumerate(NAMES, start=1):
    v, r1, _ = ph.read1ByteTxRx(port, i, ADDR_VOLTAGE)
    t, r2, _ = ph.read1ByteTxRx(port, i, ADDR_TEMP)
    if r1 != scs.COMM_SUCCESS:
        print(f"{i} {n:13s} 응답 없음 ({ph.getTxRxResult(r1)})")
        continue
    vs.append(v / 10)
    print(f"{i} {n:13s} {v / 10:4.1f} V   {t if r2 == scs.COMM_SUCCESS else '?'} °C")
port.closePort()
if vs:
    lo = min(vs)
    print(f"\n최저 {lo:.1f} V → " + ("충전/교체 필요 (6.6 V 미만)" if lo < 6.6 else "정상"))
