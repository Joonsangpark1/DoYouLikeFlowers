"""
Feetech 서보 모터가 버스에 응답하는지 직접 확인하는 진단 스크립트.
lerobot 설치 없이 feetech-servo-sdk + pyserial만으로 동작한다.

준비물: pip install feetech-servo-sdk pyserial
사용: python feetech_ping_test.py [포트]   (기본 /dev/ttyACM0, Windows에서 직접 돌리면 COM4 등)

모든 보레이트(9600~1,000,000)로 ID 1~7을 순회하며 ping을 보내고,
응답이 온 (motor_id, model_number) 조합을 전부 출력한다.
아무 baud에서도 found=[] 만 나오면 소프트웨어 문제가 아니라
배선(데이터선/전원) 문제다.
"""
import sys

import scservo_sdk as scs

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
BAUDRATES = [1_000_000, 500_000, 250_000, 128_000, 115_200, 57_600, 38_400, 19_200, 9_600]


def main():
    port_handler = scs.PortHandler(PORT)
    if not port_handler.openPort():
        print(f"포트 열기 실패: {PORT}")
        return

    for baud in BAUDRATES:
        port_handler.setBaudRate(baud)
        packet_handler = scs.PacketHandler(0)  # protocol 0 (STS/SMS 시리즈)
        found = []
        for motor_id in range(1, 8):
            model_number, comm_result, error = packet_handler.ping(port_handler, motor_id)
            if comm_result == scs.COMM_SUCCESS:
                found.append((motor_id, model_number))
        print(f"baud={baud}: found={found}")

    port_handler.closePort()


if __name__ == "__main__":
    main()
