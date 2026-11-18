# HIL-SERL 시연 데이터 수집 가이드 (게임패드)

SO-101 로봇 팔을 **게임패드로 조종해서 HIL-SERL 학습용 시연 데이터**를 모으는 방법입니다.
처음 하는 사람 기준으로 위에서부터 순서대로 따라 하면 됩니다.

> 로봇·카메라 연결(WSL, usbipd, conda, lerobot 설치)은 SmolVLA 수집과 같습니다.
> 처음이라면 `../smolvla_데이터수집/README.md`의 **0장(개념)·1장(설치)·2장(세션 시작)**을 먼저 읽으세요.
> 이 폴더의 `attach_usb.ps1`, `setup_session.sh`, `calibration/`은 그 폴더와 같은 파일입니다.

> **2026-11-17 새 방식: `record_prior.py` (VLA 종료 자세에서 시작하는 prior 시연, 카메라 2대, 손목 회전)**
> 아래 4장의 `record_demos.py`(고정 시작 자세, 카메라 1대, xyz+그리퍼)는 옛 방식입니다.
>
> | | record_demos.py (옛) | **record_prior.py (새)** |
> |---|---|---|
> | 시작 자세 | 고정 자세 | **매번 서버 SmolVLA(trial4)를 실제로 돌려서 멈춘 자세** |
> | 카메라 | 1대 (usbip) | **손목 Innomaker(5558) + 고정 C270(5559)**, 둘 다 Windows 송신기 |
> | 액션 | [dx, dy, dz, gripper] | **[dx, dy, dz, droll, gripper]** (`wrist_ee.py`, actor도 같은 걸 써야 함) |
> | 녹화 구간 | 전체 | VLA 다음, 사람 시연 구간만 |
>
> 준비 (Windows PowerShell 3개):
> 1. `..\smolvla_데이터수집\code\attach_usb.ps1` — 로봇 WSL 연결 + 손목 카메라 송신기(`--find innomaker`, 5558)
> 2. `python camera_sender_windows.py --find c270 --port 5559 --exposure -5` — 고정 카메라 (C270은 자동 노출이면 15 fps)
> 3. `gamepad_sender.ps1` — 게임패드
> 4. sior: `bash ~/lerobot_flower/start_server.sh` (policy 서버, 이미 떠 있으면 그대로)
>
> 실행 (WSL): `bash code/record_prior.sh` (이어서는 `--resume`). 미리보기 http://localhost:8080 (왼쪽 손목 / 오른쪽 고정)
>
> 게임패드: [대기] Start 시작 · LB 꽃 바꾸기 · Back 종료 / [VLA] RB 바로 넘겨받기 · B 취소 /
> [시연] 왼쪽 스틱 앞뒤·좌우, 오른쪽 스틱 위아래 = 높이, 좌우 = 손목 회전, RT 닫기 · LT 열기, Y 성공 · A 실패 · X 다시 · Back 종료

```
hilserl_시연수집/
├── README.md
└── code/                      ← 이 폴더 통째로 복사해서 쓰면 됨
    ├── gamepad_sender.ps1     [Windows] 게임패드 입력을 WSL로 보냄 (녹화 내내 켜 둠)
    ├── attach_usb.ps1         [Windows] 로봇·카메라 USB를 WSL로 넘기기 (매 세션)
    ├── setup_session.sh       [WSL] 장치 권한·캘리브레이션 확인 (매 세션)
    ├── gamepad_test.py        [WSL] 로봇 없이 게임패드 입력 확인
    ├── measure_workspace.py   [WSL] 작업 영역 + 시작 자세를 손으로 재서 config에 저장 (작업 바꿀 때 1번)
    ├── record_demos.py        [WSL] 시연 녹화
    ├── check_demos.py         [WSL] 녹화한 데이터 점검
    ├── configs/flower_hil.json   모든 설정 (장치, 속도, 작업 영역, 시간 제한, 데이터셋 이름)
    ├── lerobot_plugins.py     lerobot에 WSL 카메라 + 원격 게임패드를 끼우는 코드
    ├── usbip_camera.py        WSL 카메라 + 브라우저 미리보기
    ├── urdf/                  로봇 모델 (역기구학 계산용)
    └── calibration/           팀 공통 로봇 캘리브레이션
```

---

## 0. 개념 (5분)

### HIL-SERL이 뭔가

**HIL-SERL**(Human-in-the-Loop Sample-Efficient RL)은 **실제 로봇이 직접 해보면서 배우는 강화학습**입니다.

- 로봇이 시도 → 성공하면 보상 1, 아니면 0 → 보상을 많이 받는 쪽으로 정책이 좋아짐
- 사람이 옆에서 지켜보다가 이상하게 가면 **게임패드로 개입(RB)**해서 바로잡음 → 그 개입도 학습 데이터가 됨
- 처음부터 아무것도 모르는 상태로 시작하면 너무 오래 걸리니까, **사람이 보여준 시연 데이터를 먼저 넣고** 시작함 ← 이 폴더가 하는 일

SmolVLA는 "보고 따라 하기"(모방학습)라 시연이 많을수록 좋지만, HIL-SERL은 **시연이 출발점**일 뿐이고 실력은 그다음 온라인 학습에서 늡니다.
그래서 시연은 **10~30개** 정도면 됩니다.

### SmolVLA 데이터와 뭐가 다른가

| | SmolVLA 데이터 | HIL-SERL 시연 데이터 (이 폴더) |
|---|---|---|
| 조종 방법 | 손으로 팔을 잡고 시연 → 재생 | **게임패드**로 실시간 조종 |
| 액션 | 관절 6개 목표 각도 | **끝단(그리퍼) 이동량** `[dx, dy, dz, 그리퍼]` |
| 보상/종료 | 없음 | **성공 버튼(Y)을 누른 프레임에 보상 1**, 마지막 프레임에 done |
| 실패 에피소드 | 버림 | **저장함** (실패도 "이러면 보상 0"이라는 정보) |
| 속도 | 30 fps | **10 fps** (공식 HIL-SERL 설정) |
| 지시문 | 꼭 필요 | 기록만 됨 (정책은 문장을 안 읽음) |

### 왜 "끝단 이동량"인가

관절 6개를 직접 움직이게 하면 강화학습이 찾아야 할 경우의 수가 너무 많습니다.
그래서 HIL-SERL은 정책이 **"그리퍼를 앞으로 1cm, 위로 0.5cm"** 같은 명령만 내고, 관절 각도는 역기구학(IK)이 계산합니다.
그리고 **작업 영역 상자**(end_effector_bounds) 밖으로는 못 나가게 막아서 안전하고 빠르게 배우게 합니다.
게임패드 조종도 똑같이 끝단을 움직이는 방식이라, 사람이 낸 명령이 그대로 정책이 낼 명령과 같은 형식으로 저장됩니다.

### 컴퓨터 구성

```
 [게임패드] ─USB/무선─ Windows ── gamepad_sender.ps1 ──(localhost:5557)──┐
 [로봇 팔]  ─USB─────── Windows ──(usbipd)───────────────────────────────┼─> WSL: record_demos.py
 [웹캠]     ─USB─────── Windows ──(usbipd)───────────────────────────────┘        └─> 미리보기 localhost:8080
```

게임패드는 **WSL로 넘기지 않습니다.** WSL 리눅스에는 Xbox 패드 드라이버가 없어서 넘겨도 안 보이기 때문에,
Windows가 기본으로 가진 XInput으로 읽어서 네트워크로 보냅니다.

---

## 1. 준비물

### 게임패드

**Xbox 호환(XInput) 게임패드**여야 합니다.

| 패드 | 사용 |
|---|---|
| Xbox 컨트롤러 (유선/무선) | ✅ 그대로 |
| 8BitDo, 저가형 PC 패드 | ✅ **X-input 모드**로 (보통 전원 켤 때 버튼 조합 / 뒷면 스위치) |
| Logitech F310/F710 | ✅ 뒷면 스위치 **X** |
| PS4/PS5, 스위치 프로 | ❌ 그대로는 안 됨 (Steam/DS4Windows로 Xbox 패드처럼 보이게 하면 됨) |

연결 후 Windows에서 `Win+R` → `joy.cpl`에 패드가 보이면 OK.

### 또는: 자작 조이스틱 (Arduino Uno/Nano 또는 ESP32)

게임패드 대신 직접 만든 조이스틱을 써도 됩니다. 보드가 게임패드와 **같은 형식**으로 값을 보내므로 WSL 쪽은 바뀌는 게 없고,
2-2에서 `gamepad_sender.ps1` 대신 `serial_sender.ps1`을 켜면 됩니다.

부품: 보드 1개, 2축 썸스틱 모듈(KY-023 등) 2개, 푸시버튼 8개(개입 버튼은 크고 누르기 편한 것), 점퍼선, USB 케이블.

배선 — 버튼은 전부 **한쪽 다리는 핀, 다른 쪽은 GND** (저항 필요 없음, 내부 풀업):

| 역할 | 게임패드 대응 | Uno/Nano 핀 | ESP32 핀 |
|---|---|---|---|
| 왼쪽 스틱 VRx (좌우 → EE y) | 왼쪽 스틱 | A0 | 34 |
| 왼쪽 스틱 VRy (위아래 → EE x) | 왼쪽 스틱 | A1 | 35 |
| 오른쪽 스틱 VRx (안 씀) | 오른쪽 스틱 | A2 | 32 |
| 오른쪽 스틱 VRy (위아래 → EE z) | 오른쪽 스틱 | A3 | 33 |
| **개입 (누르는 동안)** | RB | D2 | 25 |
| 성공 | Y | D3 | 26 |
| 실패 | A | D4 | 27 |
| 다시 찍기 | X | D5 | 14 |
| 에피소드 시작 | Start | D6 | 13 |
| 그리퍼 닫기 | RT | D7 | 18 |
| 그리퍼 열기 | LT | D8 | 19 |
| Back | Back | D9 | 23 |
| 개입 중 표시 LED | — | D13 (보드 LED) | 2 (보드 LED) |

썸스틱 전원: Uno/Nano는 **5V**, ESP32는 **반드시 3.3V** (5V를 넣으면 ESP32 핀이 상할 수 있음). 스틱의 SW 핀은 안 씁니다.

업로드: Arduino IDE로 `code/joystick_fw/joystick_fw.ino`를 열고 보드(Arduino Nano / Uno / ESP32 Dev Module)와 포트를 골라 업로드.
**보드를 켤(꽂을) 때는 스틱을 만지지 마세요** — 처음 0.3초 동안 스틱 가운데 값을 잽니다.

안전: 개입 버튼 선이 빠지면 "안 누름"으로 읽혀 정책 쪽으로 돌아갑니다. USB가 빠지거나 보드가 멈추면 0.3초 안에
`serial_sender.ps1`이 "패드 없음"을 보내고 로봇이 멈춥니다. 조이스틱 보드는 **usbipd로 WSL에 넘기지 않습니다**
(Windows에 남아 있어야 COM 포트로 읽힘. `attach_usb.ps1`은 로봇 CH343만 고르게 되어 있음).

방향이 반대인 축은 펌웨어 위쪽의 `INVERT_LX/LY/RY`를 `true`로 바꿔서 다시 업로드합니다 (config의 `x_sign` 등은 1로 둠).

### 설치 (최초 1회, WSL)

SmolVLA README 1장대로 lerobot을 설치했다면 추가로:

```bash
conda activate lerobot
cd ~/lerobot
pip install -e ".[feetech,hilserl]"     # 역기구학(placo) + HIL-SERL 학습 부품
pip install simplejpeg
```

확인: `python -c "import placo, simplejpeg; print('ok')"`

---

## 2. 매 세션 시작 (5분)

### 2-1. 로봇·카메라 연결 (SmolVLA와 같음)

1. 로봇 전원 ON, 노란 점퍼 캡 **B**, USB 2개 연결, **Ubuntu 터미널 하나 열어두기**
2. Windows PowerShell(관리자):
   ```powershell
   cd "C:\Users\<윈도우계정>\Desktop\로보틱스\hilserl_시연수집\code"
   powershell -ExecutionPolicy Bypass -File attach_usb.ps1
   ```
3. Ubuntu 터미널:
   ```bash
   conda activate lerobot
   cd "/mnt/c/Users/<윈도우계정>/Desktop/로보틱스/hilserl_시연수집/code"
   bash setup_session.sh
   ```
   장치 번호가 `/dev/ttyACM0`, `/dev/video0`이 아니라고 나오면 `configs/flower_hil.json`의 `"port"`, `"index_or_path"`를 고칩니다.

### 2-2. 게임패드 송신기 켜기 — Windows PowerShell (일반 권한으로 새 창)

```powershell
cd "C:\Users\<윈도우계정>\Desktop\로보틱스\hilserl_시연수집\code"
powershell -ExecutionPolicy Bypass -File gamepad_sender.ps1
```

**이 창은 녹화가 끝날 때까지 켜 둡니다.** WSL 프로그램이 아직 안 켜졌으면 `[대기]`가 반복되는 게 정상이고,
WSL에서 프로그램을 켜면 자동으로 `[연결됨]` `[패드 OK]`로 바뀝니다.

자작 조이스틱이면 대신:

```powershell
powershell -ExecutionPolicy Bypass -File serial_sender.ps1              # COM 포트 자동 선택
powershell -ExecutionPolicy Bypass -File serial_sender.ps1 -ComPort COM5  # 여러 개라 못 고를 때
```

`[조이스틱] COM5 열림`, `[보드] {"info":"center",...}`(가운데 값, Uno는 500 전후 / ESP32는 2000 전후면 정상)가 나오고
WSL 쪽이 켜지면 `[조이스틱 OK]`가 나옵니다. 2-3의 확인 표는 그대로 쓰면 됩니다 (RT/LT = 그리퍼 닫기/열기 버튼).

### 2-3. 게임패드 확인 — Ubuntu 터미널 (처음 한 번, 패드를 바꿨을 때)

```bash
python gamepad_test.py
```

| 해보기 | 화면에 나와야 하는 것 |
|---|---|
| 왼쪽 스틱 위로 | `dx=+` |
| 왼쪽 스틱 왼쪽으로 | `dy=+` |
| 오른쪽 스틱 위로 | `dz=+` |
| RT(오른쪽 트리거) 누르기 | `gripper=0` (닫기) |
| LT(왼쪽 트리거) 누르기 | `gripper=2` (열기) |
| Y / A / X / Start / Back | `-> 버튼: Y` 등 |

> 버튼에 1·2·3·4가 적힌 일반 USB 패드(pad_mapper로 매핑한 것)는 위치 기준으로 대응합니다:
> **1(위)=Y 성공, 3(아래)=A 실패, 4(왼쪽)=X 다시 찍기**, 2(오른쪽)=B(안 씀), R1=RB 개입, R2/L2=그리퍼 닫기/열기, SELECT=Back, START=Start.

반대로 나오는 축이 있으면 `configs/flower_hil.json`의 `teleop`에서 `x_sign` / `y_sign` / `z_sign`을 `-1.0`으로 바꿉니다.
`Ctrl+C`로 끝냅니다.

---

## 3. 작업 영역·시작 자세 재기 (작업을 처음 정하거나 바꿀 때 1번)

`configs/flower_hil.json`의 `end_effector_bounds`와 `fixed_reset_joint_positions`가 `null`이면 녹화가 시작되지 않습니다.
꽃·꽃병을 실제 위치에 놓고:

```bash
python measure_workspace.py
```

1. 3초 카운트다운 뒤 **모터 힘이 빠집니다 → 팔을 손으로 받치기**
2. 작업에 필요한 범위를 **손으로 천천히 다 훑기** (꽃을 잡는 위치, 들어 올리는 높이, 옮길 위치, 그 사이 경로)
   - 너무 넓게 훑으면 학습이 느려지고, 좁으면 작업을 못 합니다. **필요한 곳 + 조금**이 기준
3. 에피소드를 시작할 자세에 팔을 두고 **Enter** (그리퍼는 열어 둔 상태로)
4. **q** → 힘이 다시 들어가고, 측정 결과가 config에 저장됩니다 (이전 파일은 `flower_hil.json.bak`)

---

## 4. 녹화

```bash
python record_demos.py                  # 처음 (새 데이터셋)
python record_demos.py --resume=true    # 이어서
```

시작까지 30초쯤 걸립니다. 미리보기: Windows 브라우저 **http://localhost:8080** (위쪽에 현재 상태가 글자로 나옴)

### 게임패드 조작

```
          LT 그리퍼 열기                      RT 그리퍼 닫기
          ┌──────┐                              ┌──────┐
     Back(종료)              Start(시작)
        ┌───┐                        Y 성공
        │ L │ 왼쪽 스틱              X 다시      B
        └───┘ ↑↓ 앞뒤(x)                  A 실패
              ←→ 좌우(y)         ┌───┐
                                 │ R │ 오른쪽 스틱 ↑↓ 높이(z)
                                 └───┘
```

### 에피소드 하나 찍는 순서

```
 [READY] 로봇이 시작 자세로 돌아와 있음 → 꽃을 제자리에 놓기 → Start
   │
 [REC]  스틱으로 그리퍼를 꽃까지 → RT로 잡기 → (작업 끝까지)
   │
   ├─ 성공했으면 Y  → 저장 (마지막 프레임 보상 1)
   ├─ 망쳤으면   A  → 저장 (실패 에피소드, 보상 0)
   ├─ 조작 실수면 X → 버림 (다시 찍기)
   └─ 시간 제한(20초) 넘김 → 실패로 저장
   │
 로봇이 시작 자세로 돌아감 → [READY]로
```

`Back`은 언제든 종료 (녹화 중이던 에피소드는 버림). 목표 개수(`num_episodes_to_record`, 기본 20)를 채우면 자동 종료.

> 🚨 녹화 중 게임패드 연결이 끊기면(송신기 창을 닫는 등) 로봇은 **그 자리에 멈춥니다.**
> 프로그램을 끄면 팔은 **마지막 자세를 유지**합니다 (힘이 안 빠짐). 전원을 끄기 전에 팔을 받치세요.

### 좋은 시연 규칙

1. **Start 누르면 바로 출발, 성공하면 바로 Y** — 가만히 있는 시간이 길면 그것까지 배움
2. **성공 판정 기준을 팀에서 하나로 정하고** 매번 같은 순간에 Y — 이 "보상"이 강화학습의 목표가 됨
3. 너무 느리지 않게. 스틱을 끝까지 밀면 초당 10cm (설정 `end_effector_step_sizes` 0.01m × 10fps)
4. **꽃 위치를 조금씩 바꿔가며** (데모 때 올 수 있는 범위 안에서) — 매번 똑같은 위치면 그 위치만 배움
5. 실패 에피소드도 몇 개 섞이는 건 괜찮음 (억지로 만들 필요는 없음)
6. 개수: **성공 위주로 10~30개**

---

## 5. 점검

```bash
python check_demos.py
```

| 확인 | 기준 |
|---|---|
| 결과 열 | 성공이 대부분이어야 함 |
| 정지비율 | 40%를 넘으면 ⚠️ — 출발이 늦거나 중간에 멈춘 시간이 김 |
| 닫기/열기 | 잡기 작업이면 닫기가 1번 이상 |
| ⚠️done 형식 / reward가 중간에 | 나오면 안 됨 (나오면 담당자에게) |

영상: `\\wsl.localhost\Ubuntu\home\<리눅스사용자>\lerobot_data\parkjoonsang\flower_hil_demo\videos`
잘못 찍은 에피소드 지우기는 SmolVLA README 6장의 `lerobot-edit-dataset ... delete_episodes`와 같습니다 (`--repo_id`, `--root`만 이 데이터셋으로).

### 업로드

`configs/flower_hil.json`에서 `"push_to_hub": true`로 바꾸면 종료할 때 Hugging Face에 올라갑니다 (`hf auth login` 필요).

---

## 6. 설정 파일 (`configs/flower_hil.json`) 주요 항목

| 항목 | 기본값 | 뜻 |
|---|---|---|
| `env.fps` | 10 | 1초에 몇 번 명령/기록 (공식 HIL-SERL 값) |
| `robot.port`, `cameras.front.index_or_path` | `/dev/ttyACM0`, `/dev/video0` | 장치 경로 |
| `robot.max_relative_target` | 10 | 한 스텝에 관절이 최대 몇 도까지 움직일 수 있나 (안전장치) |
| `teleop.x_sign`/`y_sign`/`z_sign` | 1 | 스틱 방향 뒤집기 |
| `teleop.swap_gripper` | false | RT/LT가 반대로 동작하면 true |
| `teleop.deadzone` | 0.15 | 스틱을 이만큼 이상 밀어야 움직임 |
| `reset.fixed_reset_joint_positions` | (측정) | 에피소드 시작 자세 (관절 6개) |
| `reset.control_time_s` | 20 | 에피소드 시간 제한 (넘으면 실패로 저장) |
| `inverse_kinematics.end_effector_bounds` | (측정) | 작업 영역 상자 (m, 로봇 바닥 기준 x 앞, y 왼쪽, z 위) |
| `inverse_kinematics.end_effector_step_sizes` | 0.01 | 스틱을 끝까지 밀었을 때 한 스텝 이동량 (m) |
| `image_preprocessing` | null | 영상 자르기/축소. 시연은 원본 해상도로 찍고 나중에 정함 (7장) |
| `dataset.repo_id` / `task` | `parkjoonsang/flower_hil_demo` | 데이터셋 이름 / 작업 설명 |
| `dataset.num_episodes_to_record` | 20 | 이번 실행에서 찍을 개수 |

명령줄에서 바꿀 수도 있습니다: `python record_demos.py --dataset.num_episodes_to_record=5 --env.processor.reset.control_time_s=30`

> ⚠️ 시연을 찍기 시작한 뒤에는 `fps`, `end_effector_step_sizes`, 시작 자세를 바꾸지 마세요.
> 액션의 의미(스틱 1 = 몇 cm)가 바뀌어서 앞의 데이터와 섞이면 학습이 헷갈립니다. 바꿔야 하면 새 데이터셋 이름으로.

---

## 7. 다음 단계 (학습 쪽, 아직 미구현)

1. **영상 자르기 범위 정하기**: HIL-SERL은 작업 영역만 잘라서 128x128로 줄인 영상을 씁니다.
   공식 `python -m lerobot.rl.crop_dataset_roi --repo-id ...`는 OpenCV 창이 필요해서 WSL에서는 안 뜹니다 → Windows나 학습 서버에서 실행
2. config에 `image_preprocessing.crop_params_dict`, `resize_size: [128, 128]` 반영
3. 학습 서버에서 learner, 로봇 옆 노트북에서 actor 실행. actor도 같은 카메라·게임패드를 써야 하므로
   `lerobot_plugins`를 import한 뒤 `lerobot.rl.actor`를 실행하는 래퍼가 필요 (이때 `always_intervene: false` → **RB를 누르는 동안만 개입**)

아직 안 정한 것 (팀 결정 필요, `꽃꽃이/PROGRESS.md` "미결정"):
잡기와 꽂기를 정책 하나로 할지 둘로 나눌지, 꽂기 성공 판정을 이미지 분류기로 할지 센서로 할지.
이 도구는 어느 쪽이든 쓸 수 있습니다 — 작업마다 config를 복사해서 `task`, `repo_id`, 작업 영역, 시작 자세만 바꾸면 됩니다.

---

## 8. 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| `[gamepad] 포트 5557에서 대기 중`에서 안 넘어감 | Windows에서 `gamepad_sender.ps1`이 켜져 있는지. 켜져 있는데 `[패드 없음]`이면 패드 연결/X-input 모드 확인 |
| 송신기에 계속 `[대기]` | WSL 프로그램이 아직 안 켜짐 (정상). 켰는데도 그러면 포트 번호가 config의 `teleop.port`와 같은지 |
| `Address already in use` | 이전에 켠 프로그램이 아직 돌고 있음 → 그 터미널에서 Ctrl+C, 또는 `pkill -f record_demos` |
| 스틱 방향이 반대 | `x_sign`/`y_sign`/`z_sign`을 -1로 |
| RT를 눌렀는데 그리퍼가 열림 | `swap_gripper: true` |
| 로봇이 어느 방향으로 더 안 감 | 작업 영역 상자 끝에 닿은 것 (정상). 더 필요하면 `measure_workspace.py` 다시 |
| `EE jump ... > 0.05m` 에러로 멈춤 | 한 스텝에 5cm 넘게 움직이려 함 → `end_effector_step_sizes`가 너무 큼, 또는 시작 자세가 작업 영역 밖 |
| `fixed_reset_joint_positions가 비어 있음` | 3장 `measure_workspace.py` 먼저 |
| `이미 있습니다 ... --resume=true` | 이어서 찍으려면 `--resume=true` |
| 미리보기 접속 안 됨 / 카메라 에러 | SmolVLA README 8장 카메라 항목과 같음 |
| `Missing motor IDs` | SmolVLA README 8장과 같음 |
| `Text-to-speech command failed: spd-say` 경고 | 무시해도 됨 (lerobot이 음성 안내를 시도하는 것) |

---

## 9. 코드 설명 (궁금한 사람만)

- **공식 부품을 그대로 씀**: 관측 처리, 끝단 이동 → IK → 관절 명령, 작업 영역 제한, 시간 제한, 보상/종료 처리는
  `lerobot.rl.gym_manipulator`의 `make_robot_env` / `make_processors` / `step_env_and_process_transition`을 그대로 호출합니다.
  나중에 HIL-SERL actor가 쓰는 것과 같은 코드라서 데이터 형식이 정확히 맞습니다.
- **녹화 루프만 새로 짬** (공식 `gym_manipulator --mode=record` 대비):
  이어서 녹화 가능, Ctrl+C로 꺼도 데이터셋 정상 마무리, 에피소드 사이 고정 5초 대기 대신 Start 버튼,
  시작 자세 복귀를 속도 제한(30도/초)으로, 시연 중 RB 안 눌러도 조종, 브라우저 미리보기에 상태 표시.
- **lerobot_plugins.py**: config `"type": "usbip_camera"` / `"remote_gamepad"`로 쓸 수 있게 lerobot에 등록.
  게임패드 버튼은 "눌린 순간" 한 번만 이벤트가 되고, 대기 중에 누른 버튼은 녹화 시작 때 버려집니다.
- **검증**: 실제 로봇 없이 가짜 로봇 + 스크립트 게임패드로 성공(Y)/다시(X)/실패(A)/시간 초과/종료(Back)/이어서 녹화를 끝까지 돌려서
  저장 형식, 보상 위치, 스틱 방향(왼쪽 스틱 위 → +x, 오른쪽 → −y, 오른쪽 스틱 위 → +z), 그리퍼(RT → 100)를 확인함.
  **실제 로봇·실제 게임패드로는 아직 안 돌려봄** → 첫 실행 때 2-3장 게임패드 확인과 로봇 방향 확인을 꼭 할 것.
