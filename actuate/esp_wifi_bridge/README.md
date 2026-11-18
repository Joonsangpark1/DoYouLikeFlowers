# ESP32 WiFi 브릿지 — SO-101을 케이블 없이 조작하기

## 구조
```
[노트북 WSL2, lerobot]  <--WiFi/TCP-->  [ESP32]  <--UART-->  [SO-101 서보버스]
        (socat로 가상 시리얼 포트 생성)         (바이트 그대로 중계, 프로토콜 해석 없음)
```
ESP32는 프로토콜을 전혀 모르고, 그냥 TCP로 받은 바이트를 UART로, UART로 받은 바이트를 TCP로
그대로 넘기기만 한다. lerobot 입장에서는 USB 케이블 대신 WiFi로 연결된 시리얼 포트가 하나
더 생긴 것과 동일하게 보인다 — feetech-servo-sdk나 lerobot 코드는 전혀 손댈 필요 없음.

## ⚠️ 배선 전 반드시 확인할 것
- SO-101 서보버스가 half-duplex(선 하나로 송수신 공유)인지, full-duplex(TX/RX 분리)인지
- 버스 전압이 3.3V인지 5V인지 — **ESP32는 3.3V 로직**이라 5V 버스에 레벨시프터 없이
  직결하면 ESP32가 손상될 수 있다
- 지금 쓰는 구동보드(예: Waveshare 서보 드라이버 보드)의 정확한 핀 배치

이 정보 없이 `esp32_wifi_serial_bridge.ino`의 UART_RX_PIN/UART_TX_PIN을 실제 서보버스에
연결하지 말 것. 보드 모델/사진 확인되면 정확한 배선을 다시 정리해줄 수 있음.

## 사용 순서

### 1. ESP32에 펌웨어 플래시
`esp32_wifi_serial_bridge.ino`를 Arduino IDE로 열고:
- `WIFI_SSID`, `WIFI_PASSWORD`를 실제 값으로 채운다
- 보드 선택 후 업로드
- 시리얼 모니터(115200 baud)를 열어서 `IP: xxx.xxx.xxx.xxx` 로그 확인 → 이 IP를 기록

### 2. (배선 확인 후) ESP32 UART를 서보버스에 연결
위 경고 항목을 다 확인한 뒤에만 진행.

### 3. WSL에서 가상 시리얼 포트 생성
```bash
chmod +x connect_esp_bridge.sh
./connect_esp_bridge.sh <1단계에서 확인한 ESP IP>
```
이 터미널은 계속 띄워둔 채로 둔다(포그라운드 실행, 종료하면 가상 포트도 사라짐).

### 4. lerobot에서 평범한 포트처럼 사용
다른 터미널에서, 지금까지 `--robot.port=/dev/ttyACM0` 같은 자리에 그대로 대입:
```bash
lerobot-teleoperate \
  --teleop.type=keyboard_ee \
  --robot.type=so101_follower --robot.port=$HOME/ttySO101_wifi --robot.id=my_follower
```

## 트러블슈팅
- ESP 시리얼 모니터에 IP가 안 찍힘 → WiFi SSID/비밀번호 확인, 2.4GHz 대역인지 확인(ESP32는 5GHz 미지원)
- `connect_esp_bridge.sh`가 연결 거부됨 → ESP가 재부팅됐거나 IP가 바뀌었을 수 있음(공유기 설정에서 고정 IP 권장)
- lerobot에서 포트가 안 열림 → `ls -la $HOME/ttySO101_wifi`로 심볼릭 링크가 실제로 생겼는지 확인
- 응답이 오긴 하는데 깨짐/타임아웃 → WiFi 지연/패킷 손실 문제일 수 있음, 유선(USB) 대비 신뢰성이
  떨어질 수 있다는 점 감안 — 데모 수집처럼 타이밍이 중요한 작업엔 아직 검증 안 된 경로임
