// ESP32 WiFi <-> UART 브릿지 (SO-101 서보버스용)
//
// 역할: PC(lerobot)가 보면 이 ESP가 "네트워크 너머의 USB-시리얼 어댑터"처럼 보이게 한다.
// PC -> (WiFi/TCP) -> 이 ESP -> (UART) -> SO-101 서보 버스
// 그 반대 방향(서보 응답 -> PC)도 그대로 중계한다. 프로토콜 해석은 전혀 하지 않는
// 순수 바이트 패스스루이므로, lerobot(feetech-servo-sdk) 쪽 로직은 손댈 필요 없다.
//
// !!! 배선 전 확인 필수 !!!
// SO-101 서보버스가 half-duplex(단일 선) TTL인지, 전압이 3.3V/5V 중 무엇인지,
// 쓰고 있는 구동보드(Waveshare 등)의 정확한 핀 배치를 먼저 확인할 것.
// 확인 전에는 UART_RX_PIN/UART_TX_PIN을 서보버스에 연결하지 말 것 — ESP32는 3.3V
// 로직이라 5V 버스에 그대로 물리면 보드가 손상될 수 있다.

#include <WiFi.h>

const char* WIFI_SSID = "your-ssid";      // TODO: 채우기
const char* WIFI_PASSWORD = "your-pass";  // TODO: 채우기

const uint16_t TCP_PORT = 8880;
const uint32_t BUS_BAUD = 1000000;  // Feetech STS/SCS 버스 기본 1Mbps -- 실제 값 확인 필요

// UART2 핀 (일반 ESP32 devkit 기준 예시 -- 실제 배선 확정 전까지는 가짜 값으로 취급할 것)
const int UART_RX_PIN = 16;
const int UART_TX_PIN = 17;

WiFiServer server(TCP_PORT);
WiFiClient client;

void setup() {
  Serial.begin(115200);  // USB 디버그 콘솔
  Serial2.begin(BUS_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi 연결 중");
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());  // 이 IP를 PC 쪽 connect_esp_bridge.sh 인자로 사용

  server.begin();
  Serial.printf("TCP 서버 시작, port=%u\n", TCP_PORT);
}

void loop() {
  if (!client || !client.connected()) {
    WiFiClient incoming = server.available();
    if (incoming) {
      client = incoming;
      Serial.println("PC 연결됨");
    }
  }

  // TCP -> UART: PC가 보낸 서보 명령을 버스로 그대로 중계
  if (client && client.connected()) {
    while (client.available()) {
      Serial2.write(client.read());
    }
  }

  // UART -> TCP: 서보 응답을 PC로 그대로 중계
  while (Serial2.available()) {
    uint8_t b = Serial2.read();
    if (client && client.connected()) {
      client.write(b);
    }
  }
}
