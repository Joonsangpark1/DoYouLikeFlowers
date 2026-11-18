// HIL-SERL용 자작 조이스틱 펌웨어 (Arduino Uno/Nano 또는 ESP32 DevKit, 같은 파일)
//
// 게임패드 대신 쓴다. gamepad_sender.ps1이 보내던 것과 같은 JSON 한 줄을 USB 시리얼로 60Hz 송신:
//   {"pad":0,"lx":0.000,"ly":0.000,"rx":0.000,"ry":0.000,"lt":0.000,"rt":0.000,"btn":0}
// Windows에서 serial_sender.ps1이 이 줄을 그대로 WSL(포트 5557)로 넘긴다 -> WSL 쪽 코드는 그대로.
//
// 의미 (lerobot_plugins.py의 remote_gamepad와 같음):
//   왼쪽 스틱 위/아래 = EE x (앞/뒤), 왼쪽 스틱 좌/우 = EE y, 오른쪽 스틱 위/아래 = EE z
//   개입 버튼(RB)    = 누르고 있는 동안만 사람이 조종 (손 떼면 즉시 정책으로)
//   성공(Y) / 실패(A) / 다시(X) / 시작(Start) / Back = 한 번 누르기
//   그리퍼 닫기(RT) / 열기(LT)
//
// 배선: 버튼은 전부 "핀 <-> GND" (내부 풀업 사용, 누르면 LOW). 저항 필요 없음.
//   선이 빠지거나 끊기면 '안 누름'으로 읽힘 -> 개입이 저절로 켜지는 일은 없다.
// 썸스틱 모듈(KY-023 등): +5V(ESP32는 반드시 3.3V!) / GND / VRx / VRy. SW(스틱 누름)는 안 씀.
//
// 켤 때 스틱을 만지지 말 것: 처음 0.3초 동안 가운데 값을 잰다.

#if defined(ESP32)
// ESP32: ADC는 ADC1 핀(32~39)만 사용 (ADC2는 Wi-Fi와 충돌). 썸스틱 전원은 3.3V.
const uint8_t PIN_LX = 34, PIN_LY = 35, PIN_RX = 32, PIN_RY = 33;
const uint8_t PIN_RB = 25, PIN_Y = 26, PIN_A = 27, PIN_X = 14, PIN_START = 13,
              PIN_RT = 18, PIN_LT = 19, PIN_BACK = 23;
const uint8_t PIN_LED = 2;
const int ADC_MAX = 4095;
#else
// Uno / Nano
const uint8_t PIN_LX = A0, PIN_LY = A1, PIN_RX = A2, PIN_RY = A3;
const uint8_t PIN_RB = 2, PIN_Y = 3, PIN_A = 4, PIN_X = 5, PIN_START = 6,
              PIN_RT = 7, PIN_LT = 8, PIN_BACK = 9;
const uint8_t PIN_LED = 13;
const int ADC_MAX = 1023;
#endif

// 스틱 방향이 반대면 여기서 true로 (gamepad_test.py로 확인: 왼쪽 스틱 위 -> dx +, 왼쪽 -> dy +, 오른쪽 위 -> dz +)
// 모듈을 어떤 방향으로 붙였는지에 따라 다름. 여기서 맞추면 flower_hil.json의 x/y/z_sign은 1로 둔다.
const bool INVERT_LX = false, INVERT_LY = false, INVERT_RX = false, INVERT_RY = false;

const float DEADZONE_RAW = 0.04f;  // 가운데 근처 떨림 제거 (최종 deadzone은 WSL config의 0.15)
const float FULL_SCALE = 0.90f;    // 끝까지 안 밀려도 90%면 1.0 (싼 모듈은 끝값에 못 닿음)
const uint32_t PERIOD_MS = 16;     // 약 60Hz

// XInput 버튼 비트 (lerobot_plugins.py BUTTONS와 같아야 함)
const uint16_t BIT_START = 0x0010, BIT_BACK = 0x0020, BIT_RB = 0x0200,
               BIT_A = 0x1000, BIT_X = 0x4000, BIT_Y = 0x8000;

struct Btn { uint8_t pin; uint16_t bit; };
const Btn BUTTONS[] = {
  {PIN_RB, BIT_RB}, {PIN_Y, BIT_Y}, {PIN_A, BIT_A}, {PIN_X, BIT_X},
  {PIN_START, BIT_START}, {PIN_BACK, BIT_BACK},
};
const uint8_t N_BTN = sizeof(BUTTONS) / sizeof(BUTTONS[0]);

int center[4];
const uint8_t AXIS_PIN[4] = {PIN_LX, PIN_LY, PIN_RX, PIN_RY};
const bool AXIS_INV[4] = {INVERT_LX, INVERT_LY, INVERT_RX, INVERT_RY};

uint16_t stableBtn = 0, lastRawBtn = 0;  // 2번 연속 같은 값이면 확정 (~16ms 디바운스)
bool stableRT = false, stableLT = false, lastRT = false, lastLT = false;

int readAvg(uint8_t pin, uint8_t n) {
  long s = 0;
  for (uint8_t i = 0; i < n; i++) s += analogRead(pin);
  return (int)(s / n);
}

float norm(uint8_t i) {
  int raw = readAvg(AXIS_PIN[i], 4);
  int c = center[i];
  float v = raw >= c ? (float)(raw - c) / (float)(ADC_MAX - c) : (float)(raw - c) / (float)c;
  v /= FULL_SCALE;
  if (v > 1.0f) v = 1.0f;
  if (v < -1.0f) v = -1.0f;
  if (v > -DEADZONE_RAW && v < DEADZONE_RAW) v = 0.0f;
  return AXIS_INV[i] ? -v : v;
}

void printField(const char* key, float v) {
  Serial.print(",\"");
  Serial.print(key);
  Serial.print("\":");
  Serial.print(v, 3);
}

void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < N_BTN; i++) pinMode(BUTTONS[i].pin, INPUT_PULLUP);
  pinMode(PIN_RT, INPUT_PULLUP);
  pinMode(PIN_LT, INPUT_PULLUP);
  pinMode(PIN_LED, OUTPUT);
#if defined(ESP32)
  analogReadResolution(12);
#endif
  delay(300);
  for (uint8_t i = 0; i < 4; i++) {
    center[i] = readAvg(AXIS_PIN[i], 64);
    // 켤 때 스틱을 잡고 있었으면 가운데가 크게 어긋남 -> 이론적 가운데로
    if (abs(center[i] - ADC_MAX / 2) > ADC_MAX / 6) center[i] = ADC_MAX / 2;
  }
  // "pad" 키가 없는 줄은 serial_sender.ps1이 화면에만 찍고 WSL로는 안 보냄
  Serial.print("{\"info\":\"center\",\"lx\":"); Serial.print(center[0]);
  Serial.print(",\"ly\":"); Serial.print(center[1]);
  Serial.print(",\"rx\":"); Serial.print(center[2]);
  Serial.print(",\"ry\":"); Serial.print(center[3]);
  Serial.println("}");
}

void loop() {
  static uint32_t next = 0;
  uint32_t now = millis();
  if ((int32_t)(now - next) < 0) return;
  next = now + PERIOD_MS;

  uint16_t rawBtn = 0;
  for (uint8_t i = 0; i < N_BTN; i++)
    if (digitalRead(BUTTONS[i].pin) == LOW) rawBtn |= BUTTONS[i].bit;
  if (rawBtn == lastRawBtn) stableBtn = rawBtn;
  lastRawBtn = rawBtn;

  bool rt = digitalRead(PIN_RT) == LOW, lt = digitalRead(PIN_LT) == LOW;
  if (rt == lastRT) stableRT = rt;
  if (lt == lastLT) stableLT = lt;
  lastRT = rt;
  lastLT = lt;

  digitalWrite(PIN_LED, (stableBtn & BIT_RB) ? HIGH : LOW);  // 개입 중이면 LED 켜짐

  Serial.print("{\"pad\":0");
  printField("lx", norm(0));
  printField("ly", norm(1));
  printField("rx", norm(2));
  printField("ry", norm(3));
  printField("lt", stableLT ? 1.0f : 0.0f);
  printField("rt", stableRT ? 1.0f : 0.0f);
  Serial.print(",\"btn\":");
  Serial.print(stableBtn);
  Serial.println("}");
}
