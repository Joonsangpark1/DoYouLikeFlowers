#!/bin/bash
# ESP32 WiFi 브릿지를 WSL 안에서 로컬 가상 시리얼 포트로 노출한다.
#
# 이걸 띄워두면 lerobot 쪽에서는 --robot.port=$HOME/ttySO101_wifi 를
# 평범한 USB 시리얼 포트처럼 그대로 쓸 수 있다 (내부적으로는 TCP로 ESP까지 감).
#
# 사용법: ./connect_esp_bridge.sh <ESP_IP>
#   ESP_IP는 esp32_wifi_serial_bridge.ino를 플래시한 뒤 시리얼 모니터(115200)에
#   찍히는 IP 주소를 그대로 쓰면 된다.

set -euo pipefail

ESP_IP="${1:?사용법: $0 <ESP_IP>}"
PORT=8880
LINK="$HOME/ttySO101_wifi"

if ! command -v socat >/dev/null 2>&1; then
  echo "socat이 설치되어 있지 않음. 먼저 실행: sudo apt install socat"
  exit 1
fi

echo "ESP ${ESP_IP}:${PORT} -> ${LINK} 로 가상 시리얼 포트 생성 (Ctrl+C로 종료)"
echo "다른 터미널에서: lerobot-find-port 대신 --robot.port=${LINK} 를 바로 사용하면 됨"
socat -d -d pty,raw,echo=0,link="${LINK}" tcp:"${ESP_IP}":"${PORT}"
