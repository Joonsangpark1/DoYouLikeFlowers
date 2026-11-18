# 꽃꽃이 로봇 — 진행 기록 (이어서 작업하기용)

> 작업할 때마다 이 파일 맨 위 "현재 상태"와 "작업 로그"를 갱신한다. 새 대화에서는 이 파일부터 읽고 시작.
> 마감: **2026-11-30 전시회 라이브 데모** → 일반화보다 정해진 시나리오에서 확실한 성공이 우선.
> 큰 설계 논의 원문: `decisions/2026-09-24.md`, 전체 흐름: `FLOW.md`, 파트별 계획: `observe/PLAN.md`, `actuate/PLAN.md`

---

## 2026-11-16 갱신: 그리퍼 교체 → 데이터 처음부터 다시 (trial3)
- 그리퍼 교체 후 **그리퍼만 재캘리브레이션** (임시 id `gripper_tmp`로 전체 캘리브레이션 → `merge_gripper_calib.py`로 그리퍼 항목만 병합). homing 1758→1724, 범위 1342~2752 → 1257~2547 (폭 124°→113°). 팔 5축 그대로. 백업 `my_follower_arm_before_gripper_1116.json` (smolvla·hilserl 두 폴더). 다음 연결 때 lerobot이 물으면 ENTER (모터에 임시값이 써져 있음)
- 새 데이터셋 **`parkjoonsang/flower_reach_trial3`**: 꽃병 배치 3개 × 꽃 3종 × 30 = 270. 배치 = 회전 (1: sunflower/blue/rose, 2: blue/rose/sunflower, 3: rose/sunflower/blue — 꽃마다 각 칸 한 번씩). **11-16 18:08 정리**: 63개 중 61·62번(sunflower) 삭제 → 61개 (rose 30, blue 30, sunflower 1). 기록 파일 배치가 sunflower/rose/blue로 잘못 찍혀 있어 실제(2번칸 blue, 3번칸 rose)로 정정. 백업 `~/lerobot_data/parkjoonsang/flower_reach_trial3_backup_1116` + `..._collection_log_backup_1116.jsonl`. **18:43**: 91번째(episode_index 90, 배치2 첫 에피소드)가 sunflower로 찍힘 → `lerobot-edit-dataset modify_tasks`로 rose 정정 + 기록 파일 정정 (백업 `..._backup_ep90`). 원인: L로 배치 바꿀 때 순서 모드가 지시문을 안 바꾸던 버그 → 수정. 끊김 원인 = usbip 연결 리셋 (배터리 7.2 V 정상) → `usbipd attach --auto-attach` 로봇·카메라에 켜 둠. **20:40 원인 좁힘**: Windows에서 CH343·카메라가 동시에 사라짐 + 같은 때 "Power source change"(18:49/19:35/20:04/20:29) → 독(충전 겸용) 리셋 추정. 독은 게임패드 때문에 유지. 노트북 전원 설정 변경: 배터리 시 절전·화면끄기 3분→안 함 (되돌리기: `powercfg /change standby-timeout-dc 3; powercfg /change monitor-timeout-dc 3`). USB 선택적 절전·AC 절전은 원래 꺼져 있었음. 카메라 번호 바뀜 대비 `record_flower_reach.sh`가 /dev/v4l/by-id로 장치 찾음 배치 안 순서 rose 30 → blue 30 → sunflower 30. `record_dataset.py`에 `--order sequential` (한 꽃 다 차면 지시문 자동 전환), `--layouts` (쓸 배치만 지정) 추가. trial2는 옛 그리퍼라 섞지 않음
- 시작 자세(`start_pose.json`)의 그리퍼 값은 새 캘리브레이션 기준으로 다시 확인 필요

- **11-17 trial4로 처음부터 다시 수집** (`parkjoonsang/flower_reach_trial4`, trial3 183개는 보존): 새 시작 자세(어깨 들고 손목 72.6°), **손목 회전 캘리브레이션 기준점 180° 이동** (homing_offset 1528 → −520, `shift_wrist_roll.py`, 같은 자세 +179.1° → −0.9° 확인, 손목 회전 레지스터만 씀). 팀 공통 파일 2곳 + 설치본 동기화, 시작 자세 roll 179.21 → −0.79. 백업 `*_before_rollshift_1117.json`. trial3과 손목 회전 숫자가 180° 다르니 섞지 말 것
- **11-17 18:11 trial4 234개(12,677프레임) SmolVLA 학습 시작** (sior, `smolvla_trial4_1117_1811`, batch 32, 10000 step, 약 31분, mem 5.5 GB, 로그 `~/lerobot_flower/train_1117_1811.log`). 데이터는 Windows scp로 복사 (WSL에서 ssh로 바로 보내면 멈춤). GPU 비우려고 로보틱스2 img_prior_v1을 89.5만 step에서 중단. **18:43 완료, 최종 loss 0.055** (trial3 0.051과 비슷), 체크포인트 2000~10000 + last
- **11-18 trial4 오프라인 검증** (`~/lerobot_flower/eval_trial4.py` = eval_trial3과 같은 기준 + STATE_MODE, 결과 `logs/eval4_*.txt`). 사진은 각 에피소드 첫 프레임, 지시문 3개씩, 234개 전부:
  | 시작 상태 | 꽃 고르기 | 정답 지시문 | 바꾼 지시문 따름 | 궤적 오차 |
  |---|---|---|---|---|
  | 에피소드 첫 프레임 (trial3 방식) | 85% | 99% | 78% (원래 꽃 14%) | 3.1° |
  | start_pose.json (실물 시작 자세) | 66% | 87% | 55% (원래 꽃 27%) | 6.2° |
  | **trial4 첫 프레임 평균** | **92%** | 99% | **88%** (원래 꽃 6%) | 3.1° |
  trial3(바꾼 지시문 32%) 대비 섞어 모으기 효과 확인. 발견: 녹화 첫 프레임 팔꿈치가 start_pose.json보다 평균 +8.1° (최대 12°, 토크 풀면 처짐) → 실물에서 start_pose.json에 세우면 학습에 없던 상태라 66%로 떨어짐. 에피소드별 첫 상태보다 평균이 더 좋은 건 첫 상태에 에피소드 정보(=정답 꽃)가 묻어 있어서로 보임. → **VLA 출발 자세를 평균으로 통일**: `smolvla_데이터수집/code/start_pose_vla_trial4.json` {pan 3.84, lift −84.67, elbow 41.49, wflex 72.08, roll −1.98, grip 15.71}, run_remote_policy.py(기본 모델도 trial4 last로, 백업 .bak_1118)와 record_prior.py 기본값으로 지정. 녹화용 start_pose.json은 그대로
- **11-18 trial3 vs trial4 영상 품질 실측** (각 25 에피소드): 선명도(Laplacian 분산) 중앙 **trial3 7 vs trial4 188 (약 27배)**, 거의 같은 프레임 반복 8% vs 3%, 프레임 간 차이 11.1 vs 17.2. trial3 영상은 거의 흐릿한 수준 → 사용자 가설 "해상도/화질 해결이 성공 원인 중 하나" 지지. 단 섞어 모으기·시작 자세·에피소드 수도 함께 바뀌어 기여도 분리는 불가
- **11-18 Hugging Face 업로드 (비공개)**: `parkjoonsang/flower_reach_trial4` (234개), `parkjoonsang/flower_reach_trial3` (183개). collection_log.jsonl은 안 올라감 (로컬·sior에만)
- **11-17 HIL-SERL 고정 카메라 Logitech C270 구입**: Windows DSHOW index 1, 최대 1280x960, 자동 노출이면 640x480 15 fps → 노출 -5 고정으로 30 fps. 초점 고정, 화각 대각 약 55° (설치 위치 화면 확인은 아직)
- **11-17 HIL-SERL prior 시연 녹화 코드 `hilserl_시연수집/code/record_prior.py` (+ `record_prior.sh`, `wrist_ee.py`)**: 매 에피소드 시작 자세 → 서버 SmolVLA(trial4) 실제 실행 → 멈추면(1초간 관절 명령 변화 <0.5°, 2~15초) 그 자세에서 게임패드 시연만 녹화. 액션 [dx,dy,dz,droll,gripper] (사용자 선택: 손목 회전 추가, 숙임은 VLA 종료값 고정; xyz 0.8 cm/스텝, 회전 6°/스텝, 10 fps) → lerobot 공식 HIL-SERL actor는 4차원이라 actor도 wrist_ee.py를 써야 함. 카메라 2대: 손목 Innomaker(5558, VLA 입력 겸용) + 고정 C270(5559). 송신기 `camera_sender_windows.py --find innomaker|c270` (번호 대신 해상도 특성으로 찾음), smolvla attach_usb.ps1도 --find innomaker로 변경. RobotClient 하나를 에피소드마다 재사용(stub.Ready로 서버 상태만 초기화, 모델 재로딩 없음). 로그 `flower_hil_prior_collection_log.jsonl`(꽃·VLA 멈춘 이유·시간·종료 자세·결과). IK 오프라인 확인만 함 — 실물(로봇·Innomaker 연결) 테스트 아직
- **11-17 카메라는 WSL로 안 넘김 → Windows 송신기 방식**: 같은 카메라가 Windows 직접 29.7 fps / usbip 6~7 fps + 깨진 프레임 (WSL 재시작·버스 바꿔도 그대로). `camera_sender_windows.py`(Windows, JPEG를 localhost:5558로) + `net_camera.py`(WSL 수신, UsbipOpenCVCamera와 같은 read_latest 등) → WSL 수신 30.8 fps, 손상 0. `record_dataset.py --camera-source net`, `record_flower_reach.sh` 기본 net. `attach_usb.ps1`이 로봇만 WSL로 + 자동 재연결 + 카메라 떼고 송신기 실행 (`-CameraUsbip`로 예전 방식). 주의: 카메라가 WSL에 붙어 있으면 Windows index 0에 노트북 내장 카메라가 잡힘 → 송신기가 1080p 장치는 거부. HIL-SERL 폴더 스크립트/코드는 아직 usbip 카메라. **손목 회전 −179°가 ±180° 경계** → 넘어가면 시작 자세로 갈 때 한 바퀴 돎 (사용자: 기준점 이동은 보류)
- **11-17 카메라는 노트북 본체 USB에 직접** (독 X): 독에서는 영상 요청 순간 Windows "시스템에 부착된 장치가 작동하지 않습니다"로 끊김 반복(프레임 0). 본체 포트(busid 1-3)에서 5초 126프레임 = 25 fps, 실패 0 → 11-13의 "usbip 한계 약 11 fps"도 독 때문이었을 가능성. 데이터는 기존과 맞춰 10 fps 유지. 로봇은 독(3-4) 그대로. 자동 재연결 `usbipd attach --wsl --busid 1-3 --auto-attach`
- **11-17 수집 재개 설정**: 오프라인 검증 결과 trial3 모델이 지시문을 거의 안 따름 (정답 지시문 85%, 바꾼 지시문 32% = 우연 수준, 39%는 원래 에피소드 꽃으로) → 순서대로 모은 탓에 시간대 장면 단서로 꽃을 맞춘 지름길로 판단 (`sior:~/lerobot_flower/eval_trial3.py`). 남은 수집은 **섞어서(`--order balanced`)**, 저장·배치 변경 때 지시문이 추천 꽃으로 자동 전환. 109번 기록 배치2로 정정 (백업 `..._collection_log_backup_ep109.jsonl`). 현재 177개: 배치1 각 30 / 배치2 rose 31·blue 30·sunflower 26 / 배치3 0. 실물 확인(11-16 23:15~18 rose/sunflower/blue 각 20초)은 했으나 결과(어느 칸으로 갔는지) 미기록
- **11-16 22:24 SmolVLA trial3 학습 시작** (sior, tmux `train`): 177 에피소드 / 11,987 프레임 (서버 `~/lerobot_data/parkjoonsang/flower_reach_trial3`로 복사, HF 업로드 안 함), smolvla_base, batch 32, 10000 step, 2000마다 저장, 약 31분. 로그 `~/lerobot_flower/train_1116_2224.log`, 출력 `~/lerobot/outputs/train/smolvla_trial3_1116_2224`. 도착 오차 큰 7개(12,119,122,126,128,134,139) 포함된 채 학습
- 게임패드 조종: `hilserl_시연수집/code/teleop_wrist.py` 추가 (끝단 xyz + 손목 숙임 LB+오른쪽 스틱 + 회전 오른쪽 스틱 좌우, 자체 IK, 녹화 없음). lerobot 기본 경로는 방향 가중치 0.01 + 매 스텝 실제 FK 기준이라 손목이 흔들리고 처짐만큼 흘러감. WSL 실행 `~/run_teleop_wrist.sh`

## 현재 상태 (2026-11-13 기준)

| 항목 | 상태 |
|---|---|
| 데이터 | **HF `parkjoonsang/flower_reach_trial2` (비공개) 78 에피소드**, 10fps, 꽃 3종 (rose 32 / blue 30 / sunflower 16), 전부 배치 1번칸 sunflower·2번칸 rose·3번칸 blue. reach만, 그리퍼 고정. 에피소드별 배치 기록 `collection_log.jsonl` 같이 올림. 옛 `flower_reach`(5ep, 30fps, 재조립 전)는 안 씀 |
| 하드웨어 | 손목/그리퍼 재조립 → **재캘리브레이션 완료**, 새 시작 자세. 배터리 전원 (6.6V 아래면 충전, 11-13 오후 6.0V로 방전돼 팔꿈치 과부하 → 교체 후 8.8V) |
| 카메라 | WSL usbip 한계로 **약 11fps** → 10fps로 수집. 고정초점이라 가까우면 흐림. 가끔 0.5초 넘게 멈춤 (녹화 코드에서 처리) |
| 학습 서버 | **sior** (`ssh sior@100.101.102.84`, RTX 5080 16GB). 11-13 Tailscale 재로그인, HF 로그인 완료 |
| SmolVLA | trial2로 아직 학습 안 함 (sior `train_smolvla.sh`의 REPO_ID/OUT_DIR를 trial2로 바꿔야 함) |
| 그리퍼 패드 / 꽃병 | STL 설계 완료 (`Desktop\로보틱스\그리퍼_꽃병_설계`). **11-14 그리퍼 재캘리브레이션 완료** (`recenter_calibration.py --motors gripper`, 범위 119°, offset 1021→1781, range 2045~3446→1370~2724). 데스크탑 calibration 폴더 2곳 동기화 (이전본 `my_follower_arm_before_pad_1114.json`) |
| HIL-SERL | 시연 수집 도구만 있음 (가짜 로봇으로 검증), 실물 미검증 |

### 미결정 (사용자가 정할 것)
1. HIL-SERL 꽂기(insert) 성공 판정: **A 이미지 보상 분류기** vs **B 꽃병 슬롯 물리 센서(리미트스위치/IR)**
2. HIL-SERL 정책 1개(잡기→꽂기) vs 2개(단계 분리)
3. dense shaping 섞을지 (제안: 안 섞음)
4. **탐색/접근 분리** (사용자 제안): 꽃 인식 방법 (색 / open-vocab / YOLO), VLA 지시문 유지 여부, 카메라 1개 vs 고정 카메라 추가
5. 수집 목표: 배치 6개 x 30 = 180 계획이었으나 첫 배치에서 꽃당 30개씩 모으는 중 → `--per-layout` 기준(30 or 90) 확정 필요
6. 핸드오프 설계(`decisions/2026-11-13_handoff.md`)용으로 시연에 그리퍼 닫기 포함할지

---

## 환경 / 접속 정보

### 노트북 (로봇 + 카메라 연결, Joony-Notebook)
- Intel Arc라 CUDA 없음 → 학습/추론 연산은 서버에서
- WSL 배포판 `Ubuntu`, conda `~/miniforge3`, env `lerobot` (`.[async]`), lerobot 커밋 `5aa74557`
- 커스텀 스크립트 `C:\Users\A\lerobot\`
  - `record_dataset.py` — 손 시연(토크 OFF) → 재생하며 녹화 → 저장/`--push`
  - `usbip_camera.py` — WSL usbip 카메라 (MJPG 640x480, 손상 프레임 버림, 미리보기 http://localhost:8080)
  - `check_dataset.py` — 추종오차/점프 점검
  - `run_remote_policy.py` — 원격 추론 클라이언트. **기본값이 sior로 바뀌어 있음** (원본: `run_remote_policy.py.bak_desktop`)
  - `start_pose.json` — 시작 자세
- Tailscale IP `100.119.83.72`

### sior (학습 + 추론 서버) — 2026-11-09부터
- `ssh sior@100.101.102.84` (노트북 `~/.ssh/id_ed25519` 키 등록됨, 비번 불필요)
- Ubuntu 24.04 네이티브 (WSL 아님 → portproxy 필요 없음), RTX 5080 16GB, RAM 60GB
- 공용 머신: IsaacLab 등 다른 conda env 있음 → 건드리지 말 것. sudo는 비번 필요
- conda `~/miniconda3`, env **`lerobot`** (py3.12, torch 2.11+cu130), `~/lerobot` 커밋 `5aa74557`, `.[smolvla,dataset,async]` + conda ffmpeg/tmux
- tmux는 env 안에만 있음: `~/miniconda3/envs/lerobot/bin/tmux` (비대화형 ssh PATH에 없음)
- 작업 폴더 `~/lerobot_flower/`
  - `train_smolvla.sh` — 학습 명령 (smolvla_base, `front → camera1` rename, batch 8, 3000 step)
  - `start_train.sh` — tmux 세션 `train`에서 학습, 로그 `train_MMDD_HHMM.log`
  - `serve_policy.py` — 공식 policy_server + 이미지 리사이즈 끄는 패치 (학습 때 비율유지 패딩과 맞춤)
  - `start_server.sh` — tmux 세션 `policy`로 추론 서버(포트 8080), 이미 떠 있으면 재실행 안 함
- 체크포인트: `~/lerobot/outputs/train/smolvla_flower_reach/checkpoints/{001000,002000,003000,last}`

### 자주 쓰는 명령
```bash
# 학습 (sior)
ssh sior@100.101.102.84 '~/lerobot_flower/start_train.sh'
ssh sior@100.101.102.84 'tail -c 500 $(ls -t ~/lerobot_flower/train_*.log | head -1)'

# 추론 서버 (sior)
ssh sior@100.101.102.84 '~/lerobot_flower/start_server.sh'
ssh sior@100.101.102.84 '~/miniconda3/envs/lerobot/bin/tmux attach -t policy'

# 로봇 실행 (노트북 WSL, conda activate lerobot, cd /mnt/c/Users/A/lerobot)
python run_remote_policy.py --task 1      # 1=핑크 장미, 2=노란 해바라기
python run_remote_policy.py --task 2 --model /home/sior/lerobot/outputs/train/smolvla_flower_reach/checkpoints/002000/pretrained_model
```
안전장치: 시작 자세로 천천히 이동, 스텝당 최대 10도 클리핑, ESC/Space 즉시 정지, 종료 시 토크 유지.

---

## 아키텍처 (확정된 것 / 검토 중)
- observe(느린 고수준 판단)와 actuate(저수준 제어) 분리 — 확정
- actuate = **SmolVLA**(자연어 지시문 기반 coarse reach) + **HIL-SERL**(정밀 grasp/insert) 하이브리드 — 검토 중
  - SmolVLA 도착 정확도를 재서 HIL-SERL 작업 영역(workspace bound) 결정하기로 함
- frontend: Vite+React+R3F, 12슬롯 꽃병 템플릿, 장미/카네이션/안개꽃 (`frontend/`, `npm run dev`)

---

## HIL-SERL 보상 설계 논의 (2026-11-09)

LeRobot 코드 확인: `reward_classifier`, `success_threshold`(0.5), `terminate_on_success`, `gripper_penalty` 지원.

- 기본: **sparse 이진 보상** (성공=1 → 에피소드 종료, 그 외 0) + 사람 개입 + 초기 시연. dense shaping 없이 가는 게 HIL-SERL 설계 의도
- 위험: 보상 오판정 → 정책이 오판정을 노림(reward hacking)
- **잡기(grasp)**: 그리퍼 관절 위치로 판정 (닫기 명령인데 끝까지 안 닫히고 멈춤 = 쥠) + 손목 높이 상승. 학습 불필요
- **꽂기(insert)**:
  - A. 이미지 보상 분류기 (ResNet10) — 추가 하드웨어 없음. 대신 성공 직전 실패 장면(옆에 꽂힘, 걸침, 쓰러짐)을 음성 데이터로 많이 모아야 함
  - B. 꽃병 슬롯 아래 리미트스위치/IR break-beam + 아두이노 — 거의 100% 정확, 전시 데모용으로 추천. 단 꽃병 개조 필요, 가벼운 줄기는 안 눌릴 수 있음
- 공통: SmolVLA 도착 지점 주변 박스로 행동 제한(벗어나면 0으로 종료), 10~20초 타임아웃, `gripper_penalty`는 0에서 시작

---

## 작업 로그 (최신이 위)

### 2026-11-16 — HIL-SERL용 자작 조이스틱 (사용자: VLA 다음 HIL 개입용, 아두이노/ESP32 둘 다 보유, 썸스틱 2개+버튼 방식)
- `hilserl_시연수집/code/joystick_fw/joystick_fw.ino`: Uno/Nano/ESP32 공용 (`#if defined(ESP32)`로 핀만 다름). gamepad_sender.ps1과 **같은 JSON 줄**(lx/ly/rx/ry/lt/rt/btn XInput 비트)을 시리얼 115200으로 60Hz 송신 → WSL `remote_gamepad`는 그대로
  - 버튼 INPUT_PULLUP(핀↔GND): 개입 RB / 성공 Y / 실패 A / 다시 X / Start / Back / 그리퍼 닫기 RT / 열기 LT. 선 빠지면 '안 누름' = 개입 꺼짐
  - 켤 때 스틱 가운데 자동 측정, 90%에서 풀스케일, 2샘플 디바운스, 개입 중 보드 LED. ESP32는 ADC1 핀만, 스틱 3.3V
  - arduino-cli(IDE 내장)로 nano/uno/esp32 컴파일 OK. **실물 보드·배선은 미검증**
- `code/serial_sender.ps1`: COM 자동 선택(로봇 CH343 제외) → TCP 5557 중계, 0.3초 무입력/USB 빠짐이면 `{"pad":-1}` → 로봇 정지, 재연결 자동. DTR/RTS 끔(ESP32 리셋 방지). 문법 검사만 함, 실행 미검증
- `attach_usb.ps1` 수정: 로봇을 이름 'CH34'로도 고르던 것 → CH343(1a86:55d3) 우선, CH340(7523) 제외. CH340 나노/ESP32 조이스틱을 같이 꽂으면 로봇 인식 실패하던 문제
- README 1장(부품·핀표)/2-2(serial_sender 실행) 추가
- **같은 날 실제 게임패드 연결**: XInput 아님 — 저가형 PS 모양 패드 `VID_0810 PID_0001` (DirectInput). ANALOG 불 꺼져 있으면 왼스틱 디지털(-1/0/1), 오른스틱이 면버튼 1~4로 나옴 → **ANALOG 켜야 함**
  - `code/pad_mapper.ps1` 새로 (안내 따라 하나씩 눌러 `pad_map.json` 저장), `gamepad_sender.ps1`에 winmm 일반 패드 fallback 추가 (XInput 없으면 pad_map.json으로 같은 JSON 송신)
  - 매핑 결과 `code/pad_map.json`: 4축 모두 아날로그 OK, ly=Y(-), lx=X(+), **ry=Z(-), rx=R(+)** (오른스틱 축이 보통과 반대), 버튼 R1=32 △=1 ○=2 ×=4 □=8 L1=16 L2=64 R2=128 SELECT=256 START=512
  - 임시 매핑+로컬 리스너로 sender 출력 형식 확인 OK. **WSL `gamepad_test.py`까지 끝단 확인은 사용자 사정으로 중단 → 다음에 이어서** (sender 켜고 gamepad_test.py로 방향/버튼 확인)

### 2026-11-15 — 녹화 시작 시 카메라 warmup 타임아웃 수정
- `record_flower_reach.sh --resume`가 `camera.connect()`에서 `TimeoutError ... after 1000 ms` (장치 /dev/video0 = Innomaker 맞음, v4l2-ctl 스트리밍 12~14fps 정상)
- 원인: 한동안 안 쓴 카메라를 처음 열면 첫 장 뒤 1초 넘게 멈춤 (연결 5회 중 첫 번째만 실패, 이후 16fps·최대 간격 0.07s)
- `smolvla_데이터수집/code/usbip_camera.py` warmup: 타임아웃은 넘기고 최대 warmup_s+5초 기다림 (`WARMUP_GRACE_S`). 수정 후 5회 연결 OK, 단 그때 카메라가 이미 깨어 있어서 **차가운 첫 연결 상황은 재검증 안 됨**

### 2026-11-13 — sior Tailscale 재연결 + 학습 전 점검
- sior가 2일간 offline → 서버가 다른 계정/로그아웃 상태였음 → `sudo tailscale up --force-reauth`로 joon9991 재로그인, IP 그대로 100.101.102.84
- 점검: SSH OK, RTX 5080 (policy 서버가 ~3GB 사용 중), 디스크 217G 남음, torch cuda OK, lerobot 5aa74557, HF 다운로드 OK
- sior HF 로그인 완료 (`parkjoonsang`, 11-13). 노트북 WSL도 parkjoonsang 로그인됨
- 데이터는 여전히 Hub/노트북 모두 flower_reach 5ep뿐 (10-04 이후 추가 수집 없음)
- **수집 시작하려다 막힘: wrist_roll(id 5) Overload** — Space(시작 자세 이동) 때마다 발생. 레지스터 읽어보니 goal 664(=-121.5°) / pos 1952(≈-8°)로 막혀 있었음.
  원인: 사용자가 손목/그리퍼를 **분해 후 재조립** → 같은 숫자(-121.5°)의 실제 방향이 바뀌어 케이블/기구에 걸림. 모터 자체는 정상(전압 6.9V, 온도 23~27℃, status 0)
  - 기존 5ep는 wrist_roll이 내내 -121.5° 고정. 카메라가 그리퍼에 달려 있어 손목 각도 = 화면 기울기
  - 예전 첫 프레임을 `Desktop\로보틱스\smolvla_데이터수집\예전_시작화면.png`로 저장
  - **다음(보류, 노트북 충전 후)**: attach_usb → setup_session → record 대기 상태에서 Z/Space 금지, T/G로 미리보기를 예전 화면 기울기에 맞춤 → ESC →
    wrist_roll 읽어서 `start_pose.json`의 wrist_roll만 수정 (smolvla_데이터수집/code + C:\Users\A\lerobot 둘 다)
  - **결정(사용자)**: 예전 5ep는 안 씀 → 새 데이터셋 **`parkjoonsang/flower_reach_trial2`**로 처음부터 수집. 옛 `flower_reach`(Hub+노트북)는 지우지 않고 보관
    - `smolvla_데이터수집`의 record_flower_reach.sh 기본 REPO_ID와 README를 trial2로 변경. 첫 녹화는 `--resume` 없이
    - 학습 시 sior `train_smolvla.sh`의 REPO_ID/OUT_DIR도 trial2로 바꿔야 함 (아직 안 바꿈)
- **재캘리브레이션 (11-13)**: 예전 데이터 안 쓰므로 새로 함. lerobot-calibrate 2번 다 가운데 자세가 어긋나 shoulder_lift/wrist_flex가 360° 랩어라운드
  → `smolvla_데이터수집/code/recenter_calibration.py` 새로 만듦 (관절을 끝에서 끝까지 움직이면 범위 가운데=2047로 offset/range 재계산, 파일+모터 기록. 패드 단 뒤 `--motors gripper`로 재사용)
  - 결과 범위: pan 212°, lift 194°, elbow 194°, wflex 209°, gripper 123° (원래 손가락 기준), wrist_roll offset 1462→936
  - 공용 캘리브레이션 두 폴더 갱신 (이전 것 `my_follower_arm_before_1113.json`), WSL 백업 ~/my_follower_arm_backup_1113.json
  - 옛 start_pose.json → `start_pose_before_1113.json` (새 캘리브레이션에선 무의미). `C:\Users\A\lerobot\start_pose.json`(원격추론용)도 옛 값 → 새 시작 자세 정해지면 동기화
  - 빈 trial2 폴더 삭제 (첫 녹화 때 --resume 없이 새로 생성)
  - **새 시작 자세** (손으로 잡아 저장하는 `save_start_pose.py` 새로 만듦): pan -22.0, lift -95.9, elbow 27.0, wflex 103.7, roll -0.1, grip 4.4
    → 범위 끝에 붙어 있어서 다시 저장 (save_start_pose.py에 카메라 미리보기 추가)
    **최종(19:59)**: pan -23.5, lift -87.7, elbow 29.4, wflex 90.7, roll -0.1, grip 4.6 → 끝까지 여유 lift 9.4° / wflex 13.5°, FK TCP (0.145, 0.046, 0.175) m
    `C:\Users\A\lerobot\start_pose.json`에도 복사 (옛 것 start_pose_before_1113.json)
  - URDF 0자세 = ㄱ자(위팔 수직, 아래팔·손목 수평 앞) 그림 `smolvla_데이터수집/캘리브레이션_기준자세.png`. FK가 맞는지(ㄱ자에서 관절값≈0) 아직 확인 안 함
- **카메라 fps 한계 발견 → trial2를 10fps로**: 첫 녹화에서 카메라 실제 11.6fps. 밝기/노출/동적프레임 바꿔도 10.7~12fps,
  v4l2 원본 스트림도 11.0fps(손상 0) → WSL usbip 전송 한계. 30fps 데이터셋엔 같은 프레임이 2~3번 반복 저장됨
  - 사용자 결정: 10fps로 녹화 (HIL-SERL도 10fps). `record_flower_reach.sh` 기본 `--fps 10`, 궤적 점프 검사를 속도 기준(450°/s ÷ fps)으로 변경
  - 30fps로 찍은 시험 에피소드는 `~/lerobot_data/_archive/flower_reach_trial2_30fps_test*`로 옮김 → trial2는 처음부터 (첫 실행 --resume 없이)
  - README 삭제 명령 수정: `lerobot-edit-dataset`은 `--new_root`를 `--root`와 같게 줘야 제자리 수정 (안 주면 ~/.cache에 따로 저장)
  - 대안(미착수): 카메라를 Windows에서 읽어 WSL로 송신하면 30fps 가능할 것
- **꽃 3종으로 확장** (사용자): pink rose / blue flower / yellow sunflower. `record_flower_reach.sh` 지시문 3개 + `--flower rose/blue/sunflower`
  - `record_dataset.py`에 꽃병 칸 배치 기록 추가: L 키로 6가지 배치 선택, 저장 시 `~/lerobot_data/parkjoonsang/flower_reach_trial2_collection_log.jsonl`에
    episode_index / task / layout / target_slot(1~3) 기록 + "가장 적게 모인 (꽃 x 칸) 조합" 추천. 실물 녹화로는 아직 미검증
  - 수집량 제안: 9조합(꽃3 x 목표칸3) x 조합당 ~10 = 약 90개 (파일럿 36개 먼저 → 학습/롤아웃 후 확대). 판단은 사용자
  - **수집 진행 (20:13~21:30경)**: 78개 (rose 32 / blue 30 / sunflower 16), 전부 배치 5 (1 sunflower, 2 rose, 3 blue).
    사용자 확인: 30·45번(rose 라벨)도 실제 rose로 감 → 라벨 전부 맞음
    - 사고 1: 종료 중 USB(usbip)가 빠져 프로세스가 커널 대기(D, usb_kill_urb)로 좀비화 → `kill -9` 안 됨 → `wsl --shutdown`으로 해결. 데이터는 finalize 끝난 뒤라 무사 (45ep, 영상 프레임 수 일치 확인)
    - 사고 2: 다시 켜면 지시문이 1번(rose)으로 돌아감 → 시작 시 현재 배치 추천 지시문으로 자동 설정 + `>>> 현재 지시문 <<<` 크게 표시로 수정
    - 사고 3: 팔꿈치(id3) Overload — 목표 29° / 실제 56°로 못 올라감. 원인: **배터리 방전 (6.9V → 6.0V)**. 교체 후 8.7~8.9V. 모터 전압 보호 4~14V, 모델 777(STS3215)
    - 사고 4: 시연 중 카메라 프레임 542ms 정체 → read_latest TimeoutError로 종료 (78ep는 finalize됨). 수정: 미리보기/대기/시연은 30초까지 허용,
      재생(=저장되는 구간)만 1초 넘게 멈추면 그 에피소드 버리고 다시 재생하게 (`REC_MAX_FRAME_AGE_MS`)
    - 표시 버그: per-layout 30(꽃당 10) 기준이라 `rose 31/10`처럼 보임 — 사용자가 꽃당 30개씩 모으는 중이라 기준 확인 필요
  - **학습 준비 (11-13)**: sior `train_smolvla.sh`를 환경변수로 바꿈 (기본 REPO_ID=trial2, batch 32, 10000 step, OUT_NAME=smolvla_trial2_날짜; 옛 것 .bak_1109),
    `start_train.sh`가 REPO_ID/OUT_NAME/STEPS/BATCH 전달. 시험 실행: batch 32에서 5.3 step/s(10k ≈ 31분), GPU 9.7GB(추론서버 3.2GB 포함) → 사용자가 직접 돌리기로 해서 1분 만에 중단·출력 삭제
  - **학습 완료 (사용자 실행, 21:46~22:18)**: `~/lerobot/outputs/train/smolvla_trial2_78ep/checkpoints/{002000..010000,last}` (sior). loss 1.12 → 0.030
    - 오프라인 점검 `~/lerobot_flower/eval_offline.py <ckpt>` (짝수 에피소드 첫 프레임, 정답 지시문 궤적 오차 + 지시문 3개 바꿔치기 → 예측 끝 자세가 어느 꽃 평균에 가까운지)
      | ckpt | 궤적 평균 오차 lift/wflex | 끝 자세 오차 lift/wflex | 바꿔치기 맞음 |
      | 4000 | 6.9 / 7.2° | 2.6 / 3.0° | 94/117 |
      | 6000 | 5.1 / 5.1° | 2.2 / 2.7° | 90/117 |
      | last(10000) | 3.4 / 3.4° | 1.4 / 1.6° | 93/117 (80%) |
      틀린 건 주로 sunflower 지시문 → rose로 감 (11~15회). sunflower 데이터가 16개로 적음. 실제 로봇 롤아웃은 아직
    - **HF 업로드**: `parkjoonsang/smolvla_flower_reach_trial2_78ep` (비공개, last=10000 step, 869MB)
  - **HF 업로드 (11-13)**: `parkjoonsang/flower_reach_trial2` **비공개**로 78ep 업로드 + `collection_log.jsonl`(에피소드별 배치/목표 칸). 공개 전환은 사용자 판단
  - **사용자 결정 (20:10)**: trial2 전부 삭제 후 새로 시작. **배치마다 30개(꽃당 10개) x 6배치 = 180개** 먼저, 이후 추가.
    첫 배치 1번칸 sunflower / 2번칸 rose / 3번칸 blue (= 배치 5). `--layout`, `--per-layout 30` 추가, 추천은 현재 배치 안에서 덜 모인 꽃 → 다 차면 다음 배치 안내
    (실제 녹화 1회로 jsonl 기록 동작 확인 후 삭제함)
- 사용자 제안: **탐색(베이스 돌리며 꽃 찾기)과 접근 분리**. 인식 방법(색 / open-vocab / YOLO), VLA 지시문, 카메라 수는 미결정. 손목 카메라는 고정초점이라 가까우면 흐림
- 핸드오프 설계 문서화: `decisions/2026-11-13_handoff.md` (사용자 설계 + 구현 간극 메모). 분석 스크립트는 착수 전 중단됨 (시작 자세 작업 우선)
- **넓은 그리퍼 패드 + 꽃병 설계** `Desktop\로보틱스\그리퍼_꽃병_설계\` (README, make_parts.py, stl/)
  - 원래 부품 재출력 없이 손가락에 씌우는 교체형 패드 (폭 40mm, 뒤 열린 U자, 손가락 뒤를 가로지르는 M2x30+너트 2개로 잠금). flat / stemV(가로 줄기 홈) 2종, 고정·움직임 쪽 한 쌍씩
  - 닫힐 때 두 접촉면이 평행하게 맞닿도록 설계 → 닿는 각도 URDF -8.5° (원래 손가락 끝 -11.3°) → 끝까지 닫으면 패드끼리 밀어서 과부하 가능
  - **11-14 수정 (사용자 요청)**: 고무판 1mm 자리 (`RUBBER_T=1.0`, 출력면을 1mm 뒤로, 미끄럼 홈 제거, stemV 홈 깊이 +1) → 고무끼리 닿는 각도 -6.9°.
    움직이는 쪽 패드 나사가 1개만 벽에 걸리던 버그 수정: 뒤쪽 절단 평면을 손가락 뒷면 두 점 대신 두 나사 중심 + 4mm로 → 양쪽 패드 나사 2개 모두 벽 안 (점검 통과)
  - 꽃병: 바닥 지름 80, 높이 80, 내경 12 + 깔때기 32, 바닥 무게추 홈. 3개 출력
  - **3구 꽃병** `flower_holder_x3.stl` (사용자 요청, 한 판): 210x70x80, 구멍 간격 70mm, 바닥 앞쪽에 칸 번호 점 1/2/3 (p_f 격자 칸 기록용)
  - **호 3구 꽃병** `flower_holder_arc3.stl` (사용자 요청: 호 모양 + 간격 넓게): 반지름 250 호, 간격 85 (19.6°), 250x90x80, 호 중심=로봇 베이스면 세 꽃 거리 동일. 도면 `도면_꽃병호3구.png`
  - 도구: CadQuery(STEP 읽기) + trimesh/manifold3d, venv `C:\Users\A\.venvs\cad`. 간섭 검사(전 열림 범위)·겹침 0 확인. **실물 출력/끼움 미확인**
  - **11-14 그리퍼 재캘리브레이션**: 처음엔 모터 6개 전부 응답 없음(포트 ACM0은 열림 → 전원/배선 문제), 해결 후 `recenter_calibration.py --motors gripper` → 범위 119°, offset 1781, range 1370~2724. 키보드 그리퍼 조작은 기존 `record_dataset.py` 대기 상태 y/h 키
  - **11-14 전체 재캘리브레이션 + 새 시작 자세**: s키(shoulder_lift −)가 안 먹던 원인 = 시작 자세가 lift 범위 끝 근처. recenter로 pan/lift/elbow/wflex/gripper 다시 (범위 pan 237°, lift 209°, elbow 195°, wflex 213°, gripper 124°), 데스크탑 calibration 2곳 동기화. 중간에 모터 5(wrist_roll) 응답 없음 → 재연결로 복구. 새 시작 자세 pan 9.76 / lift −91.21 / elbow 25.19 / wflex 93.14 / roll 58.33 / grip 0.64 (code/start_pose.json + C:/Users/A/lerobot/start_pose.json, 이전은 start_pose_before_1114.json). **캘리브레이션·시작 자세가 바뀌어서 기존 trial2 78ep와 관절값 기준이 다름**
  - **11-14 (이어서) 최종**: 손목 회전이 헛돎 → 그리퍼-혼 나사 풀림, 다시 조임. 이후 5관절 재캘리브레이션 (pan 243°, lift 210°, elbow 198°, wflex 217°, gripper 124°), wrist_roll이 0~4095 경계(raw 13)에 걸려 한쪽으로 못 돎 → 똑바른 그리퍼 방향을 0°로 Homing_Offset 936→1528 (범위 0~4095 유지). **최종 시작 자세** pan 11.6 / lift −87.5 / elbow 20.6 / wflex 92.0 / roll −1.0 / grip 16.3 (범위 여유 lift 17°, wflex 16°). code/start_pose.json + C:/Users/A/lerobot/start_pose.json, calibration 3곳 동기화 (이전 my_follower_arm_before_roll_1114.json)
  - **11-14 라벨 수정**: ep 122~130 (9개, 배치 rose/blue/sunflower)이 실제 rose인데 blue로 저장됨 → 프레임 task_index, 에피소드 메타 tasks/통계, stats.json, 배치 로그(target_slot 1) 전부 rose로 수정. 백업 `~/lerobot_data/parkjoonsang/backup_before_relabel_1114/`. 수정 후 133ep 8075프레임, rose 75 / blue 38 / sunflower 20. → 같은 날 HF 비공개 업로드 갱신 (133ep, collection_log.jsonl 포함, 허브에서 다시 받아 확인)
  - trial2 수집은 패드 단 뒤에 시작해야 함 (손목 카메라에 보이는 그리퍼 모양이 바뀜)

### 2026-11-11 — HIL-SERL 시연 수집 도구 (게임패드) `Desktop\로보틱스\hilserl_시연수집\`
- 공식 `lerobot.rl.gym_manipulator`의 make_robot_env/make_processors/step_env_and_process_transition 그대로 사용 → actor와 같은 데이터 형식
  (action `[dx,dy,dz,gripper]` -1~1 + 0닫기/1유지/2열기, next.reward, next.done, discrete_penalty, 10fps, 영상 원본 해상도)
- `lerobot_plugins.py`: config type `usbip_camera`(WSL 카메라+미리보기 상태 글자), `remote_gamepad`(TCP 5557 수신, 공식 GamepadTeleop과 같은 의미:
  RB 개입/Y 성공/A 실패/X 다시). WSL 커널에 xpad 없음 → 패드는 Windows `gamepad_sender.ps1`(XInput, 설치 불필요)이 localhost로 송신
- `record_demos.py`: 녹화 루프만 직접 (공식은 resume 불가·Ctrl+C시 finalize 안 됨·5초 고정 대기). Start로 에피소드 시작, 속도제한 복귀, always_intervene
  - 함정: `from __future__ import annotations` 쓰면 lerobot parser.wrap이 config 타입을 못 읽음
  - config의 env에 `"type"` 넣으면 draccus 에러 (env 필드가 HILSerlRobotEnvConfig 구체 타입)
- `measure_workspace.py`: 토크 끄고 손으로 훑어 EE bounds + Enter로 시작 자세 → config에 기록 (공식 find_joint_limits는 리더암 필요)
- `configs/flower_hil.json`: fps 10, step 0.01m, control_time 20s, max_relative_target 10, disable_torque_on_disconnect false, task 임시 "Grasp the flower stem."
- 검증: 가짜 로봇+스크립트 패드로 성공/다시/실패/시간초과/종료/resume 끝까지 OK, 왼스틱↑=+x, 왼스틱→=−y, 오른스틱↑=+z, RT→gripper 100.
  실제 sender(PowerShell)→WSL 수신 OK. **실제 로봇·실제 패드는 미검증** (특히 gripper 100이 실제로 닫힘인지 → 아니면 swap_gripper)
- 남은 것: crop ROI(공식 도구는 cv2 창 필요 → WSL 불가), actor 래퍼, 미결정 1~3번

### 2026-11-10 — 데이터 수집 가이드+코드 정리 (`Desktop\로보틱스\smolvla_데이터수집\`)
- 초보자용 `README.md` (개념 → 설치 → 세션 시작 → 녹화 → 점검 → 업로드/병합 → 문제 해결)
- `code/`: 노트북 `C:\Users\A\lerobot\`의 record_dataset/usbip_camera/check_dataset/feetech_ping_test/start_pose 복사
  - record_dataset.py: `--robot-port`, `--camera` 옵션 추가 (녹화 로직 변경 없음), feetech_ping_test: 포트 인자
  - 새 스크립트: `attach_usb.ps1`(CH343·Innomaker 자동 인식 bind/attach, 내장 카메라는 자동 선택 안 함),
    `setup_session.sh`(장치 확인·chmod·카메라 index0 노드 찾기·공용 캘리브레이션 설치), `record_flower_reach.sh`(지시문 고정)
  - `calibration/my_follower_arm.json`: 노트북 WSL 캘리브레이션 사본 (다른 사람이 재캘리브레이션하면 데이터 못 합침)
- 다른 PC 수집자는 각자 repo-id로 녹화 → `lerobot-edit-dataset --operation.type merge`로 병합하도록 안내
- 검증: WSL에서 setup_session.sh / record --help / check_dataset(기존 5ep) 실행 OK. 실제 로봇 연결 녹화는 안 해봄

### 2026-11-09 — sior로 이전 + SmolVLA 재학습
- 데스크탑 `irreplaceable-1`이 tailnet에서 사라짐 (오프라인 아님, 목록에 아예 없음) → **sior를 학습 서버로 쓰기로 결정**
- 노트북 SSH 키를 sior에 등록, conda env `lerobot` 새로 구축 (lerobot `5aa74557`, 노트북과 같은 커밋)
- 5ep / 3000 step / batch 8 재학습: 15 step/s, **약 3분** (4060 Ti 때 8분), 최종 loss **0.035**
- 체크 추론: 데이터셋 프레임 기준 예측과 실제 행동 차이가 관절당 1~3도, 추론 0.3초
- `serve_policy.py`를 sior로 옮기고 tmux `policy`로 실행, 노트북 Windows/WSL 양쪽에서 8080 접속 확인
- 노트북 `run_remote_policy.py` 기본 서버/모델 경로를 sior로 변경
- HIL-SERL 보상 설계 논의 (위 섹션)

### 2026-10-04 — 첫 데이터셋 + 원격 추론 end-to-end
- 수집 방식 확정: 키보드/IK가 어려워 **손 시연(토크 OFF) → 재생하며 녹화**. 리더 암은 안 삼
- HF `parkjoonsang/flower_reach` 5ep 공개 (task 1 `Move the gripper close to the pink rose.`, task 2 `... yellow sunflower.`)
- smolvla_base 카메라 키가 camera1~3이라 `front → camera1` rename 필요
- lerobot 기본 OpenCVCamera는 WSL에서 'Bad file descriptor' → usbip 카메라 전용 래퍼
- 데스크탑에서 학습 → async_inference 원격 추론 동작 (추론 0.27~0.38s)
- 공식 서버가 이미지를 비율 무시 256x256으로 줄이는 걸 끄는 패치 (`serve_policy.py`)
- 공식 클라이언트는 rename_map을 서버에 안 넘김 → 클라이언트가 처음부터 camera1로 보냄
- 로봇이 실제로 장미 쪽으로 갔는지는 확인 못 함

### 2026-09-24 — 아키텍처 논의 + 데스크탑 원격 인프라
- 상세: `decisions/2026-09-24.md`

---

## 다음 할 일 후보
- [ ] 로봇 연결 후 `run_remote_policy.py --task 1/2`로 실제 롤아웃, 장미/해바라기 쪽으로 가는지 관찰
- [ ] 지시문당 ~50ep 추가 수집 (꽃 배치 바꿔가며, 두 꽃 항상 같이) → sior에서 재학습 (steps 늘리기)
- [ ] SmolVLA 도착 정확도 측정 → HIL-SERL 작업 영역 결정
- [ ] HIL-SERL 미결정 사항 결정 후 구현
