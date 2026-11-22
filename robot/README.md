# robot/ — SO-101 꽃꽂이 로봇 실물 코드

말로 꽃을 지시하면("pink rose") 로봇 팔이 손목 카메라로 꽃을 찾아가고(**SmolVLA**), 이어서 줄기를 집어 다른 통으로 옮겨 놓는 것(**HIL-SERL**, 준비 중)을 목표로 하는 코드입니다.
처음 보는 사람이 **이 폴더만 받아서 같은 실험을 다시 할 수 있도록** 정리했습니다.

진행 기록(무엇을 왜 바꿨는지, 실험 수치)은 `../PROGRESS.md`가 기준입니다.

---

## 0. 지금 어디까지 됐나 (2026-11-22)

| 단계 | 상태 |
|---|---|
| SmolVLA 데이터 | 540 에피소드 = 꽃병 배치 6가지 × 꽃 3종(rose / blue / sunflower) × 30, 10 fps (`parkjoonsang/flower_reach_trial4`, 비공개) |
| SmolVLA 학습 | `smolvla_base` 파인튜닝 + 도착 후 정지 프레임 20장 + 이미지 증강 + 관절 상태 노이즈 2°. 학습 사진 기준 꽃 고르기 86%, 지시한 꽃으로 가는 비율 89% |
| SmolVLA 실물 | 꽃이 서로 가리지 않으면 대부분 맞는 꽃으로 감. **가려진 꽃(특히 장미)은 자주 틀림** |
| HIL-SERL | 고정 카메라·작업 영역·시연 녹화 도구 완성, 실물 시연 수집 시작 단계. 보상 분류기·강화학습은 아직 |

---

## 1. 전체 구성

```
 [Windows 노트북]                                  [GPU 서버 (RTX 5080 16GB)]
  ├─ camera_sender_windows.py  손목 카메라 → 5558      ├─ 학습: train_smolvla.sh
  ├─ camera_sender_windows.py  고정 카메라 → 5559      └─ 추론 서버: serve_policy.py (8080)
  ├─ gamepad_sender.ps1        게임패드   → 5557              ▲
  └─ usbipd                    로봇 USB를 WSL로               │ 네트워크 (우리는 Tailscale)
        │                                                     │
        ▼                                                     │
 [WSL Ubuntu, 같은 노트북]  ── 로봇 제어·녹화·VLA 실행 ─────────┘
```

- 카메라는 WSL로 넘기지 않고 **Windows에서 사진을 보내는 방식**입니다. WSL(usbip)로 넘기면 6~11 fps로 떨어지고 깨진 프레임이 나와서 바꿨습니다.
- 로봇(USB 시리얼)만 `usbipd`로 WSL에 붙입니다.

| 폴더 | 어디서 실행 | 내용 |
|---|---|---|
| `smolvla_데이터수집/` | Windows + WSL | SmolVLA 데이터 수집 (손으로 시연 → 재생하며 녹화), 캘리브레이션 도구, 시작 자세. **자세한 안내는 이 폴더 README** |
| `hilserl_시연수집/` | Windows + WSL | HIL-SERL 시연 녹화(`record_prior.py`), 게임패드 조종, 작업 영역 측정, 점검 도구. **자세한 안내는 이 폴더 README** |
| `laptop/` | WSL | `run_remote_policy.py` (서버의 SmolVLA로 실물 실행), `go_start_pose.py` |
| `server/` | GPU 서버 | 학습·추론 서버·오프라인 평가 스크립트, `lerobot_patch/` (LeRobot 수정분) |
| `그리퍼_꽃병_설계/` | — | 그리퍼 패드·꽃병 홀더 CAD 코드와 STL |

---

## 2. 준비물

**하드웨어**

| 품목 | 우리가 쓴 것 | 비고 |
|---|---|---|
| 로봇 팔 | SO-101 follower (Feetech STS3215 × 6) | 리더 암은 안 씀 (손 시연은 토크 끄고 직접 움직임) |
| 전원 | 배터리 (완충 때 모터 전압 약 9V) | **6.6V 아래면 교체.** 1시간 남짓 쓰면 9V → 6V까지 떨어짐 (11-22 측정) |
| 손목 카메라 | Innomaker U20CAM-720P | SmolVLA 입력. 640×480 |
| 고정 카메라 | Logitech C270 | HIL-SERL 보상 판정용. 로봇 뒤 위쪽, 꽃병 3개 + 놓는 통이 한 화면에 |
| 게임패드 | Xbox 호환 또는 일반 USB 패드(1·2·3·4 버튼) | 일반 패드는 `pad_mapper.ps1`로 매핑 |
| 노트북 | Windows 11 + WSL2 Ubuntu | USB 포트가 부족하면 독 사용 (8장 문제 해결 참고) |
| GPU 서버 | Ubuntu, RTX 5080 16GB | 12GB 이상이면 batch 32 학습 가능 |

**소프트웨어 버전** (다른 버전이면 데이터 형식·동작이 달라질 수 있어 고정)

| | 버전 |
|---|---|
| LeRobot | 커밋 `5aa74557` (0.6.2) + `server/lerobot_patch/flower_5aa74557.patch` |
| Python (WSL·서버) | 3.12 (conda env 이름 `lerobot`) |
| Python (Windows, 송신기용) | 3.11 + `opencv-python`, `numpy` |
| usbipd-win | 5.3 |
| placo (역기구학) | 0.9.15 |

---

## 3. 설치 (처음 한 번)

### 3-1. Windows

```powershell
wsl --install -d Ubuntu          # 재부팅 후 Ubuntu 사용자 만들기
winget install usbipd             # 로봇 USB를 WSL로 넘기는 도구
pip install opencv-python numpy   # 카메라 송신기용 (Windows Python)
```

### 3-2. WSL Ubuntu와 GPU 서버 (둘 다 같은 방법)

```bash
# conda (miniforge)
curl -L -O https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b && ~/miniforge3/bin/conda init && exec bash
conda create -n lerobot python=3.12 -y && conda activate lerobot
conda install -c conda-forge ffmpeg -y

# LeRobot을 우리 버전으로 고정 + 수정분 적용
git clone https://github.com/huggingface/lerobot.git ~/lerobot
cd ~/lerobot && git checkout 5aa74557
git apply <이 저장소>/robot/server/lerobot_patch/flower_5aa74557.patch
pip install -e ".[feetech,smolvla]"
pip install placo            # 노트북만: 게임패드 끝단 조종(역기구학)
hf auth login                # Hugging Face 데이터셋을 올리거나 받을 때
```

`flower_5aa74557.patch`가 바꾸는 것 (둘 다 환경 변수/옵션을 안 주면 원래 동작과 같음):
- `lerobot_train.py`: `FLOWER_STATE_NOISE_STD`(도)만큼 학습 배치의 관절 상태에 가우시안 노이즈. 배치마다 시작 자세가 1°쯤 달라서 모델이 사진 대신 관절값으로 배치를 외우던 지름길을 끊음
- `transforms.py`: `image_transforms.p_original` 확률로 증강 없이 원본 사진 사용

### 3-3. 코드 놓는 곳

- 노트북: 이 저장소를 Windows 쪽 아무 데나 받고, WSL에서는 `/mnt/c/...` 경로로 같은 폴더를 씁니다.
- GPU 서버: `robot/server/` 안의 파일을 `~/lerobot_flower/`로 복사합니다 (스크립트가 이 경로를 가정).

### 3-4. 로봇 캘리브레이션 (자기 로봇이면 반드시)

`*/code/calibration/my_follower_arm.json`은 **우리 로봇 전용**입니다. 다른 로봇은 자기 값으로 다시 잡아야 합니다.

```bash
lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/ttyACM0 --robot.id=my_follower_arm
```

관절 몇 개만 다시 잡을 때는 `smolvla_데이터수집/code/recenter_calibration.py --motors gripper` (끝에서 끝까지 움직이기만 하면 됨).
⚠️ 캘리브레이션을 바꾸면 관절값 기준이 달라져서, **그 전에 모은 데이터·학습한 모델과 섞어 쓰면 안 됩니다.**

---

## 4. 매번 시작할 때 (연결)

Windows PowerShell에서:

```powershell
cd <이 저장소>\robot\hilserl_시연수집\code
powershell -ExecutionPolicy Bypass -File reconnect.ps1    # 로봇 USB → WSL + 송신기 3개(손목·C270·게임패드) 시작
powershell -ExecutionPolicy Bypass -File dock_watch.ps1   # (독을 쓰면) 끊겼다 붙을 때 자동 재연결. 창 열어 두기
```

WSL에서 점검:

```bash
conda activate lerobot
cd "/mnt/c/.../robot/hilserl_시연수집/code"
python volt.py           # 모터 6개 전압·온도 (6.6V 아래면 배터리 교체)
python check_cams.py     # 손목(5558)·고정(5559) 카메라 fps (10 넘으면 OK)
python pad_raw.py 5      # 게임패드 입력 5초 (스틱·버튼 범위 확인)
```

GPU 서버에서 추론 서버 (VLA를 쓰는 작업일 때):

```bash
bash ~/lerobot_flower/start_server.sh     # tmux 세션 policy, 포트 8080
```

---

## 5. SmolVLA: 데이터 수집 → 학습 → 실물

### 5-1. 데이터 수집 — `smolvla_데이터수집/README.md`

손으로 팔을 움직여 시연하고, 그 궤적을 재생하면서 녹화합니다. 꽃병 배치 6가지를 섞어서(`--order balanced`) 모읍니다.

```bash
bash smolvla_데이터수집/code/record_flower_reach.sh            # 처음
bash smolvla_데이터수집/code/record_flower_reach.sh --resume   # 이어서
```

### 5-2. 학습 (GPU 서버)

```bash
cd ~/lerobot_flower
# 1) 에피소드마다 도착 자세를 20프레임 더 붙인 데이터셋 만들기
#    (안 하면 도착 뒤 행동이 학습에서 빠져서 모델이 멈출 줄 모름)
SRC=~/lerobot_data/<사용자>/flower_reach_trial4 DST=~/lerobot_data/<사용자>/flower_reach_trial4_hold20 HOLD=20 python build_hold.py

# 2) 학습 (tmux 세션 train, 10000 step, batch 32 → RTX 5080에서 약 35분)
STATE_NOISE=2 AUG=1 P_ORIG=0.2 REPO_ID=<사용자>/flower_reach_trial4_hold OUT_NAME=my_run \
  bash start_train.sh ~/lerobot_data/<사용자>/flower_reach_trial4_hold20
```

| 환경 변수 | 뜻 |
|---|---|
| `STATE_NOISE` | 관절 상태 노이즈 표준편차(도). 우리는 2 |
| `AUG` / `P_ORIG` | 이미지 증강 켜기 / 원본 그대로 쓰는 비율 (증강 종류는 `aug_tfs.json`) |
| `STEPS` / `BATCH` | 기본 10000 / 32 |

결과는 `~/lerobot/outputs/train/<OUT_NAME>/checkpoints/last/pretrained_model`.

오프라인 평가: `eval_trial4.py <모델> 3` (학습 사진에서 지시문을 바꿔 가며 꽃 고르기), `eval_realframes_1121.py <모델>` (실물 첫 사진), `st_swap.py <모델>` (관절 상태만 바꿔 넣어도 예측이 같은지 = 상태 지름길 검사).

### 5-3. 실물 실행 (노트북 WSL)

```bash
export FLOWER_SERVER=<서버IP>:8080
export FLOWER_MODEL=/home/<서버사용자>/lerobot/outputs/train/my_run/checkpoints/last/pretrained_model
python laptop/run_remote_policy.py --task rose        # rose / blue / sunflower
```

로그·사진·영상이 `D:\data\flower\policy_runs\`에 남습니다.

---

## 6. HIL-SERL 시연 녹화 — `hilserl_시연수집/README.md`

한 에피소드 = **VLA가 꽃 앞까지 감 → 사람이 게임패드로 줄기를 집어 옆 통에 놓음 → 성공/실패 표시**. 사람이 조종한 구간만 녹화합니다.

```bash
cd "/mnt/c/.../robot/hilserl_시연수집/code"
python record_prior.py --repo-id <사용자>/flower_hil_prior --num-episodes 30 --layout "sunflower,rose,blue"
```

- `--layout`은 **로봇 기준 왼쪽부터 실제 꽃 순서** (기록용, VLA는 안 봄)
- 미리보기: Windows 브라우저 http://localhost:8080 (손목 / 고정 카메라)
- 처음엔 화면에 `ANALOG?`가 뜸 → 패드 ANALOG 불 켜고 **오른쪽 스틱을 한 번 끝까지** 밀어야 START가 먹음

| 버튼 (일반 패드) | 하는 일 |
|---|---|
| START | 에피소드 시작 (그리퍼를 먼저 35°로 닫고 VLA 출발) |
| L1 | 대기 중 꽃 바꾸기 |
| R1 | VLA 중에 바로 넘겨받기 |
| 왼쪽 스틱 / 오른쪽 스틱 | 앞뒤·좌우 / 위아래 = 높이, 좌우 = 손목 회전 |
| R2 / L2 | 그리퍼 닫기 / 열기 |
| **1 (0.4초 꾹)** | 성공 → 그 자리에서 1.5초 더 녹화 (보상 분류기의 성공 사진) |
| **3 (0.4초 꾹)** | 실패 저장 |
| **4 (0.4초 꾹)** | 버리고 다시 |
| **2 (0.4초 꾹)** | VLA가 잘못 감 → 그 순간 사진·자세를 `<repo>_vla_fail/`에 기록하고, **VLA가 온 길을 거꾸로 되돌아가** 같은 꽃으로 다시 |
| SELECT | 버리고 종료 |

주요 옵션: `--vla-gripper 69`(VLA 동안 실제 그리퍼, 0=끝까지 열림·100=닫힘, 69≈35° 열림), `--vla-gripper-state 15.9`(VLA에 보여 주는 그리퍼 값, 6장 아래 주의), `--control-time-s 60`, `--success-frames 15`.

데이터 현황: `bash hil_data_status.sh`

> **주의: 학습 때 거의 고정이던 입력을 바꾸면 VLA가 망가집니다.**
> VLA 학습 데이터에서 그리퍼 상태는 평균 15.9, 표준편차 0.2였습니다. 실제 그리퍼를 69로 닫고 그 값을 그대로 넣으면
> 정규화 뒤 표준편차 265배 밖 값이 들어가서 엉뚱한 데로 갑니다. 그래서 `record_prior.py`는 VLA에게만 그리퍼 상태를 15.9로 보여 줍니다.

작업 영역(`configs/flower_hil.json`의 `end_effector_bounds`)은 `measure_workspace.py`로 손으로 훑어서 잰 뒤, 필요한 만큼만 남겼습니다:
x 0.075~0.398, y −0.278~+0.15, z −0.001~0.30 m (로봇 바닥 기준 x 앞, y 왼쪽, z 위). 놓는 통은 로봇에서 270 mm, 오른쪽 60°.

---

## 7. 그리퍼 값

| 값 | 상태 |
|---|---|
| 0 | 끝까지 열림 (약 115°) |
| 15.4 | SmolVLA 학습 데이터 (약 97° 열림) |
| 60 / 69 | 약 45° / 35° 열림 |
| 100 | 닫힘 |

집게를 혼에 다시 끼우면 이 대응이 틀어집니다. `grip_read.py`(토크 안 건드리고 읽기)로 손으로 닫고 열어 값을 확인하세요.

---

## 8. 자주 생긴 문제 (실제로 겪은 것)

| 증상 | 원인 / 해결 |
|---|---|
| `/dev/ttyACM0` 없음, 녹화 중 `Input/output error` | 독이 리셋되며 USB 번호(busid)가 바뀜. `reconnect.ps1` 실행. `dock_watch.ps1`을 켜 두면 자동. **로봇 전원을 껐다 켤 때도 독이 리셋됨** |
| 노트북이 독을 아예 인식 못 함 | 노트북 충전기를 독에 꽂았을 때 생김 → 충전기는 본체에 |
| 카메라가 `Unknown USB Device (Port Reset Failed)` | 독 포트가 오류 상태 → 독 케이블을 노트북에서 뺐다 꽂기 |
| 독에 카메라 2대를 꽂으면 1대만 열림 | 독 USB 대역폭 부족 → 카메라 1대는 본체 포트로 |
| 카메라 송신기 창이 바로 꺼짐 | 카메라가 아직 준비 안 됨. 송신기는 60초까지 다시 시도하므로 잠시 뒤 다시 |
| 송신기가 노트북 내장 카메라를 잡음 | 손목 카메라가 빠진 상태에서 켜짐 → 꽂은 뒤 송신기 다시 켜기 |
| `[gamepad] sender 연결됨`에서 멈춤 | 송신기가 패드를 못 찾음(`{"pad":-1}`) → 패드·독 연결 확인 후 `gamepad_sender.ps1` 다시 |
| 오른쪽 스틱이 안 먹음 / 저절로 성공·실패 저장 | 일반 패드 **ANALOG 꺼짐** (오른쪽 스틱이 버튼 1~4로 들어옴). ANALOG 불 켜기 |
| 모터 하나가 `Missing motor IDs` / 응답 없음 | 대부분 **배터리 전압 저하**. `volt.py`로 확인, 6.6V 아래면 교체 후 로봇 전원 껐다 켜기 |
| 게임패드 조종이 거의 다 "못 감" | 팔이 접힌 쉬는 자세(팔꿈치가 URDF 범위 밖)에서 시작. `teleop_wrist.py`는 시작 자세로 먼저 이동함 |
| VLA가 특정 꽃을 못 찾음 | 시작 화면에서 그 꽃이 다른 꽃에 가려짐. 꽃송이가 서로 겹치지 않게 |
| 녹화 시작 때 `이미 있음. --resume` | 저장된 에피소드가 있는 폴더. 이어서 하려면 `--resume` (빈 폴더는 자동으로 지우고 시작) |

---

## 9. 내 환경에 맞게 바꿔야 하는 곳

| 무엇 | 어디 |
|---|---|
| Hugging Face 이름 `parkjoonsang/...` | 녹화 명령의 `--repo-id`, 학습의 `REPO_ID` |
| 서버 주소·모델 경로 | 환경 변수 `FLOWER_SERVER`, `FLOWER_MODEL` (기본값은 우리 서버) |
| 서버 경로 `~/lerobot_flower`, `~/miniconda3` | `server/*.sh` (tmux·conda 경로) |
| 로컬 저장 위치 `D:\data\flower` | `laptop/run_remote_policy.py`, `capture_start.py`, `view_c270.py` |
| 평가 스크립트의 데이터셋 경로 `~/lerobot_data/parkjoonsang/...` | `server/eval_*.py`, `st_swap.py` 맨 위 (평가용 실물 사진 `realframes_1121/`은 저장소에 없음) |
| 캘리브레이션 | 3-4 |
| 시작 자세 | `smolvla_데이터수집/code/start_pose_vla_trial4.json` (우리 데이터 첫 프레임 평균). 자기 데이터면 다시 계산 |
