# SmolVLA 데이터 수집 가이드 (flower_reach)

SO-101 로봇 팔로 **SmolVLA 학습용 데이터**를 모으는 방법을 처음 하는 사람 기준으로 설명합니다.
위에서부터 순서대로 따라 하면 됩니다.

- 작업 내용: 지시문(문장)에 따라 그리퍼를 **핑크 장미** 또는 **노란 해바라기** 근처로 가져가기 (그리퍼는 안 씀)
- 데이터셋: https://huggingface.co/datasets/parkjoonsang/flower_reach_trial2 (2026-11-13부터 새로 수집. 손목 재조립 전 데이터 `parkjoonsang/flower_reach` 5ep는 보관만 하고 안 씀)
- 목표: **지시문당 약 50 에피소드, 총 100개** (SmolVLA 공식 권장: 25개로는 부족, 50개부터)

```
smolvla_데이터수집/
├── README.md                 ← 지금 이 문서
└── code/                     ← 이 폴더 통째로 복사해서 쓰면 됨
    ├── attach_usb.ps1        [Windows] 로봇·카메라 USB를 WSL로 넘기기 (매 세션)
    ├── setup_session.sh      [WSL] 장치 권한·캘리브레이션·장치 번호 확인 (매 세션)
    ├── record_flower_reach.sh[WSL] 녹화 시작 (지시문 고정된 단축 명령)
    ├── record_dataset.py     녹화 프로그램 본체 (시연 → 재생 → 저장)
    ├── usbip_camera.py       WSL에서 카메라 안정적으로 여는 코드 + 브라우저 미리보기
    ├── check_dataset.py      녹화한 데이터 점검 (수치 + 그래프)
    ├── feetech_ping_test.py  모터가 응답 안 할 때 하드웨어 진단
    ├── start_pose.json       팀 공통 시작 자세
    └── calibration/my_follower_arm.json   팀 공통 로봇 캘리브레이션
```

---

## 0. 먼저 개념부터 (5분)

### SmolVLA는 무엇을 배우나

SmolVLA는 **"카메라 영상 + 로봇 관절 상태 + 문장"을 보고 "다음에 관절을 어떻게 움직일지"를 출력**하는 모델입니다
(VLA = Vision-Language-Action). 그래서 데이터의 한 프레임(1/30초)은 이렇게 생겼습니다.

| 항목 | 내용 | 예 |
|---|---|---|
| `observation.images.front` | 그 순간의 카메라 사진 (640x480) | 테이블 위 장미·해바라기 |
| `observation.state` | 그 순간의 관절 6개 각도 | `[17.3, -73.8, 31.2, 82.1, -121.5, 8.6]` |
| `action` | 그 순간 모터에 보낸 목표 각도 = **정답** | 다음 위치 |
| `task` | 지시문 문장 | `Move the gripper close to the pink rose.` |

에피소드 = 시작 자세에서 꽃까지 가는 한 번의 동작(보통 5~10초, 150~300프레임). 이걸 100개쯤 모읍니다.

### 왜 "손으로 가르치고 → 재생하며 녹화"하나

| 방법 | 문제 |
|---|---|
| 키보드로 조종 | 관절이 하나씩 계단식으로 움직임 → 모델이 그 어색한 동작까지 배움 |
| 리더 암(조종용 팔) | 좋지만 비쌈 |
| **손 시연 → 재생 (우리 방식)** | 사람이 팔을 직접 잡고 자연스럽게 움직이고, 로봇이 그걸 그대로 다시 하면서 녹화 |

| 단계 | 하는 일 | 저장되는 것 |
|---|---|---|
| ① 시연 | 모터 힘을 빼고, 손으로 팔을 잡고 꽃까지 움직임 | 관절 궤적만 (영상 X) |
| ② 재생 | 꽃을 제자리에 두고, 로봇이 궤적을 그대로 재생 | 영상 + 관절 → 데이터셋 |

재생할 때 녹화하니까 **영상에 사람 손이 안 찍힙니다** (손이 찍히면 모델이 "손을 따라가기"를 배울 수 있음).

### 왜 꽃 두 개를 항상 같이 놓나

장미만 놓고 장미 데이터, 해바라기만 놓고 해바라기 데이터를 찍으면 모델은 문장을 무시하고 **"보이는 꽃으로 가기"**만 배웁니다.
**두 꽃을 항상 같이 두고 지시문만 바꿔서** 찍어야 모델이 문장을 읽고 목표를 고르게 됩니다.

### 컴퓨터 구성

```
 [로봇 팔] ─USB─┐
                ├─ Windows 노트북 ──(usbipd로 USB 전달)──> WSL(Ubuntu) 안에서 녹화 프로그램 실행
 [웹캠]   ─USB─┘                                               │
                                                               └─> ~/lerobot_data/ 에 저장 → Hugging Face 업로드
```

로봇 코드(lerobot)는 리눅스용이라 **WSL**(Windows 안의 리눅스)에서 돌립니다. 그런데 WSL은 USB 장치를 직접 못 봐서,
`usbipd`로 Windows의 USB를 WSL에 "넘겨주는" 작업을 **매 세션마다** 해야 합니다. (재부팅, USB 재연결, WSL 재시작 후 다시)

---

## 1. 최초 1회 설치

> 이미 설치된 노트북(박준상 노트북)에서 하는 거면 1-5만 확인하고 **2장으로** 넘어가세요.

### 1-1. WSL(Ubuntu) 설치 — Windows PowerShell(관리자)

```powershell
wsl --install -d Ubuntu
```

재부팅 → Ubuntu 창이 뜨면 리눅스용 사용자 이름/비밀번호 설정 (Windows 계정과 별개, 비밀번호는 `sudo` 때 씀).
이후 시작 메뉴에서 **Ubuntu**를 열면 리눅스 터미널입니다. 이 문서에서 `bash` 코드 블록은 전부 여기서 칩니다.

### 1-2. conda + lerobot 설치 — Ubuntu 터미널

```bash
# conda (파이썬 환경 관리 도구)
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3
~/miniforge3/bin/conda init bash
exec bash                                   # 터미널 새로고침. 앞에 (base)가 붙으면 성공

# lerobot (팀이 쓰는 버전으로 고정 — 다른 버전이면 데이터 형식이 달라질 수 있음)
git clone https://github.com/huggingface/lerobot.git ~/lerobot
cd ~/lerobot
git checkout 5aa74557f84c54d4b458f8b9643c5aa2982acfed
conda create -y -n lerobot python=3.12
conda activate lerobot
pip install -e ".[feetech,dataset]"        # 모터 제어 + 데이터셋 저장
pip install simplejpeg matplotlib           # 카메라 손상 프레임 검사 + 점검 그래프
```

확인: `python -c "import lerobot, simplejpeg; print('ok')"` → `ok`

### 1-3. usbipd 설치

Windows PowerShell:

```powershell
winget install usbipd       # 설치 후 PowerShell을 껐다 다시 열기. 확인: usbipd --version
```

### 1-4. 이 폴더 복사

`code/` 폴더를 통째로 원하는 곳에 둡니다. WSL에서 Windows 파일은 `/mnt/c/...`로 보입니다.

```bash
# 예: 바탕화면에 있을 때
cd "/mnt/c/Users/<윈도우계정>/Desktop/로보틱스/smolvla_데이터수집/code"
```

### 1-5. Hugging Face 로그인 (업로드할 사람만)

```bash
conda activate lerobot
hf auth login        # https://huggingface.co/settings/tokens 에서 Write 토큰 만들어 붙여넣기
```

`parkjoonsang/flower_reach_trial2`는 쓰기 권한이 있어야 올라갑니다. 권한이 없으면 7장의 "여러 사람이 모을 때" 방식으로 하세요.

### 1-6. 캘리브레이션은 하지 마세요

캘리브레이션 = "모터 숫자값 ↔ 관절 각도" 기준표입니다. 사람마다 새로 하면 **같은 자세가 다른 각도로 기록돼서 데이터를 합칠 수 없습니다.**
그래서 팀 공통 파일(`code/calibration/my_follower_arm.json`)을 쓰고, `setup_session.sh`가 자동으로 설치해줍니다.
(lerobot이 캘리브레이션 하라고 물어보면 → 공통 파일이 설치 안 된 것. `setup_session.sh`를 먼저 실행)

---

## 2. 매 세션 시작할 때 (5분)

### 2-1. 하드웨어

1. 로봇 **전원 어댑터 ON** (USB만으로는 모터가 안 움직임)
2. 로봇 보드의 **노란 점퍼 캡이 B(USB) 쪽**에 꽂혀 있는지 확인
3. 로봇 USB, 웹캠(Innomaker) USB를 노트북에 연결
4. **Ubuntu 터미널을 하나 열어두기** (WSL이 켜져 있어야 USB를 넘길 수 있음)

### 2-2. USB를 WSL로 넘기기 — Windows PowerShell (관리자 권한으로 실행)

```powershell
cd "C:\Users\<윈도우계정>\Desktop\로보틱스\smolvla_데이터수집\code"
powershell -ExecutionPolicy Bypass -File attach_usb.ps1
```

`[로봇] ... 연결 완료`, `[카메라] ... 연결 완료`가 나오면 성공.
로봇은 USB-시리얼 칩(CH343)으로, 카메라는 이름(Innomaker)으로 자동으로 찾습니다.
다른 웹캠을 쓰면 표에서 BUSID를 보고 `-CameraBusId 1-3`처럼 지정하세요. (노트북 내장 카메라를 넘기면 안 됨)

<details><summary>스크립트 없이 손으로 하는 법</summary>

```powershell
usbipd list                              # BUSID 확인 (CH343 = 로봇, Innomaker = 카메라)
usbipd bind --busid 1-1                  # 장치당 최초 1번만 (관리자 권한)
usbipd attach --wsl --busid 1-1          # 매 세션
```
</details>

### 2-3. 장치 권한 + 점검 — Ubuntu 터미널

```bash
conda activate lerobot
cd "/mnt/c/Users/<윈도우계정>/Desktop/로보틱스/smolvla_데이터수집/code"
bash setup_session.sh
```

전부 ✅이고 마지막에 `준비 완료. 녹화: bash record_flower_reach.sh --resume ...`가 나오면 그 명령을 그대로 쓰면 됩니다.
(카메라가 `/dev/video2`처럼 기본값과 다르면 `--camera` 옵션을 붙여서 알려줍니다)

---

## 3. 현장 세팅

1. 테이블에 **장미와 해바라기를 둘 다** 놓기
2. 꽃 위치를 **테이프로 표시** (재생할 때 정확히 같은 자리에 다시 놓아야 함)
3. 카메라는 녹화 내내 **움직이지 않게 고정** (세션마다 카메라 위치가 바뀌면 모델이 헷갈림)
4. 카메라 화면에 사람/손이 안 들어오게 서기

---

## 4. 녹화

### 4-1. 실행

```bash
bash record_flower_reach.sh --resume                  # 기존 데이터셋에 이어서 (보통 이것)
bash record_flower_reach.sh --resume --push public    # ESC로 끝낼 때 Hugging Face에 자동 업로드
```

- 처음으로 데이터셋을 만드는 컴퓨터면 `--resume`을 빼세요. (`already exists` 에러가 나면 반대로 `--resume`을 붙이면 됨)
- 미리보기: Windows 브라우저에서 **http://localhost:8080**
- 지시문은 스크립트 안에 고정돼 있습니다: `1` = `Move the gripper close to the pink rose.` / `2` = `Move the gripper close to the blue flower.` / `3` = `Move the gripper close to the yellow sunflower.`
- **꽃 배치 기록**: 꽃병(3칸)에 꽃을 어떻게 꽂았는지 `L` 키로 고릅니다 (6가지, 미리보기 왼쪽 위에 `L번호: 1번칸 2번칸 3번칸` 표시).
  저장할 때마다 `~/lerobot_data/parkjoonsang/flower_reach_trial2_collection_log.jsonl`에 지시문·배치·목표 꽃의 칸 번호가 한 줄씩 기록되고,
  **다음 추천**(가장 적게 모인 '꽃 x 칸' 조합)을 알려줍니다. 꽃을 실제로 바꿔 꽂은 뒤 `L`로 화면 배치를 맞추세요.
  ⚠️ 에피소드를 지우면 이 기록 파일의 번호는 자동으로 안 고쳐집니다 (지운 줄을 지우고 뒤 번호를 하나씩 당길 것)
  (직접 `python record_dataset.py --task ...`로 칠 때는 **글자 하나까지** 똑같아야 같은 작업으로 저장됨)

### 4-2. 에피소드 하나 찍는 순서

```
 [대기] ──1 or 2──> 지시문 선택 (화면 왼쪽 위 TASK 1/2)
   │
 Space ──> 시작 자세로 이동 ──> 3초 카운트다운 (⚠️ 팔을 손으로 받치기!) ──> 모터 힘 빠짐
   │
 [시연] 그리퍼 근처를 잡고 꽃까지 한 번에 쭉 ──> 도착하면 바로 Space (힘 다시 들어감)
   │
 [재생 대기] 꽃이 테이프 위치에 있는지 확인 ──> Space
   │
 [재생+녹화] 로봇이 혼자 똑같이 움직이며 녹화 (빨간 점 REC)
   │
 [확인] Space 저장 / R 다시 재생 / X 버림 ──> [대기]로
```

| 상태 | 키 | 동작 |
|---|---|---|
| 대기 | `1` / `2` / `3` | 이번 에피소드 지시문 선택 (1=장미, 2=파란 꽃, 3=해바라기) |
| 대기 | `L` | 꽃병 배치 바꾸기 (6가지 중 다음) |
| 대기 | `Space` | 시작 자세로 이동 → 3초 카운트다운 → 힘 빠짐 → 시연 시작 |
| 대기 | `Q/A` `W/S` `E/D` `R/F` `T/G` | 관절 하나씩 키보드 조종 (자세 맞출 때만) |
| 대기 | `O` / `Z` | 현재 자세를 시작 자세로 저장 / 시작 자세로 이동 |
| 시연 중 | `Space` / `X` | 시연 끝 / 버림 |
| 재생 대기 | `Space` / `X` | 재생+녹화 / 버림 |
| 재생 중 | `X` | 중단 (버림) |
| 재생 후 | `Space` / `R` / `X` | **저장** / 꽃 다시 놓고 재생 / 버림 |
| 언제든 | `ESC` | 종료 (저장 안 한 에피소드는 버려짐) |

> 🚨 **카운트다운 동안 반드시 팔을 손으로 받치세요.** 힘이 빠지는 순간 팔이 중력으로 떨어집니다.
> ESC로 프로그램을 끝내면 연결이 끊기면서 모터 힘이 빠집니다. 팔을 받치거나 낮은 자세로 내려놓은 상태에서 종료하세요.

> ⚠️ `O`는 팀 공통 시작 자세(`start_pose.json`)를 덮어씁니다. 시작 자세를 바꾸기로 합의한 게 아니면 누르지 마세요.
> 시작 자세가 바뀌면 그 전 데이터와 시작점이 달라집니다.

> 💡 키가 안 먹으면: 터미널 창을 클릭해서 포커스를 주고, **한/영 키로 영문 입력**인지 확인하세요.

---

## 5. 좋은 데이터를 위한 규칙

1. **그리퍼 근처를 잡고 꽃까지 한 번에 쭉** — 관절을 하나씩 따로 움직이지 말 것
2. **힘이 빠지면 바로 출발, 도착하면 바로 Space** — 앞뒤로 가만히 있는 시간이 길면 로봇이 "출발 안 하기"를 배움
3. **너무 빠르게 휘두르지 말기** — 한 프레임(1/30초)에 15도 넘게 움직이면 재생이 거부됨 (`점프 -> 재생 안 함`)
4. **재생 전 꽃을 시연 때와 같은 위치**(테이프)에 정확히 놓기
5. **시연 1번당 저장 1번** — `R`은 재생이 실패했을 때 재시도용 (같은 궤적 여러 번 저장 금지)
6. 매번 비슷한 경로로, 꽃 바로 앞(살짝 위)에서 멈추기 — 사람마다 "도착" 위치가 다르면 모델이 헷갈림

### 꽃 배치 계획 (추천)

- 배치 하나당: `1`(장미) 시연→저장, 꽃 그대로 두고 `2`(해바라기) 시연→저장
- 그다음 꽃 위치 변경 — **좌우 바꾸기 포함** (장미가 항상 왼쪽이면 모델이 "왼쪽으로 가기"를 배움)
- 예: 배치 5가지 × 지시문 2개 × 5회 = 50 에피소드 → 이걸 두 번 하면 100개
- 지시문별 개수를 비슷하게 (저장할 때마다 `이번 세션: 1번 n개 2번 m개` 출력됨)
- 데모 때 꽃을 놓을 위치를 미리 정했다면 그 근처 배치를 많이 넣기

---

## 6. 녹화 후 점검

```bash
python check_dataset.py --repo-id parkjoonsang/flower_reach_trial2
```

| 확인 항목 | 정상 기준 |
|---|---|
| `⚠️추종` / `⚠️튐` 표시 | 없어야 함 |
| 시작 자세 표준편차 | 1~2도 이내 |
| 장미/해바라기 끝 위치 | `shoulder_pan`(좌우 회전) 끝값이 서로 확실히 달라야 함 |
| 그래프 `code/dataset_check/ep000.png` … | 파랑(목표)과 주황(실제)이 거의 겹침 (0.2~0.3초 늦게 따라가는 건 정상) |

영상 직접 보기: Windows 탐색기 주소창에 `\\wsl.localhost\Ubuntu\home\<리눅스사용자>\lerobot_data\parkjoonsang\flower_reach_trial2\videos`

### 이상한 에피소드 지우기

번호(`[ep 3]`)를 확인한 뒤:

```bash
lerobot-edit-dataset --repo_id parkjoonsang/flower_reach_trial2 \
  --root ~/lerobot_data/parkjoonsang/flower_reach_trial2 \
  --new_root ~/lerobot_data/parkjoonsang/flower_reach_trial2 \
  --operation.type delete_episodes --operation.episode_indices "[3]"
```

`--new_root`를 `--root`와 **똑같이** 줘야 그 자리에서 고쳐집니다 (빼먹으면 결과가 `~/.cache/huggingface/lerobot/...`에 따로 저장되고 원래 폴더는 그대로).
원본은 `flower_reach_trial2_old` 폴더로 백업됩니다. 확인 후 지우세요. 지우면 뒤 에피소드 번호가 하나씩 당겨집니다.

---

## 7. 업로드와 여러 사람이 모을 때

### 데이터셋이 있는 컴퓨터에서 이어 찍을 때 (기본)

`--push public`을 붙여서 녹화하면 ESC로 끝낼 때 자동 업로드됩니다. 깜빡했으면:

```bash
python -c "from lerobot.datasets import LeRobotDataset; from pathlib import Path; \
LeRobotDataset('parkjoonsang/flower_reach_trial2', root=Path.home()/'lerobot_data/parkjoonsang/flower_reach_trial2').push_to_hub()"
```

### 다른 컴퓨터에서 따로 모을 때

다른 컴퓨터에는 기존 에피소드 파일이 없어서 같은 이름에 `--resume`으로 이어 붙이면 꼬일 수 있습니다.
**각자 다른 이름으로 저장 → 나중에 합치기**로 하세요.

```bash
# 수집하는 사람: 자기 이름으로 새 데이터셋 (처음엔 --resume 없이)
REPO_ID=<내HF아이디>/flower_reach_<이름> bash record_flower_reach.sh --push public
```

```bash
# 합치는 사람: 데이터셋 여러 개를 하나로 (Hub에서 자동으로 받아옴)
lerobot-edit-dataset --new_repo_id parkjoonsang/flower_reach_merged \
  --operation.type merge \
  --operation.repo_ids "['parkjoonsang/flower_reach_trial2', '<아이디>/flower_reach_<이름>']"
```

합치려면 **같은 lerobot 버전, 같은 캘리브레이션, 같은 시작 자세, 같은 카메라 위치, 같은 지시문 문장**이어야 합니다.

---

## 8. 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| `attach_usb.ps1`: 로봇을 못 찾음 | 로봇 전원, USB 케이블 확인. `usbipd list`에 `CH343`이 보여야 함 |
| `attach_usb.ps1`: bind가 필요 | PowerShell을 **관리자 권한으로 실행**해서 다시 |
| `attach_usb.ps1`: attach 실패 | Ubuntu 터미널을 먼저 열어두기. 그래도 안 되면 USB 뽑았다 꽂고 다시 |
| `setup_session.sh`: ❌ 장치 없음 | `attach_usb.ps1`부터 다시 |
| `Missing motor IDs` (모터 0개 응답) | 전원 어댑터 → 노란 점퍼 캡 **B** 위치 → 1번 모터 케이블 → USB·전원 껐다 켜기. 그래도 안 되면 `python feetech_ping_test.py /dev/ttyACM0` — 모든 속도에서 `found=[]`면 배선 문제 |
| lerobot이 캘리브레이션 하라고 물어봄 | `Ctrl+C`로 끄고 `bash setup_session.sh` 실행 (공통 캘리브레이션 설치) |
| `Bad file descriptor` / 카메라 안 열림 | Windows에서 `usbipd detach --busid <카메라>` → `attach_usb.ps1` 다시 → `setup_session.sh` |
| 미리보기가 까맘 | 렌즈 캡/카메라 방향 확인 |
| 미리보기 접속 안 됨 | 녹화 프로그램이 켜져 있는지, 주소가 `http://localhost:8080`인지 |
| `already exists ... --resume` | 이어 쓰려면 `--resume` 추가 |
| `--resume`인데 에러 | 이 컴퓨터에 데이터셋이 없음 → 7장 "다른 컴퓨터에서 따로 모을 때" |
| 재생 때 `점프 -> 재생 안 함` | 시연이 너무 빨랐음 → `X`로 버리고 천천히 다시 |
| `raw MJPEG 모드 미지원` 출력 | 손상 프레임 검사가 꺼진 상태 → 담당자에게 알리기 |
| 저장 후 `카메라가 데이터셋 fps보다 느려서` 경고 | 카메라가 30fps를 못 따라감 → 담당자에게 알리기 (데이터셋 fps는 중간에 못 바꿈) |
| 키를 눌러도 반응 없음 | 터미널 창 클릭(포커스), 한/영 키로 영문 입력 |

---

## 9. 코드 설명 (궁금한 사람만)

### 왜 lerobot 공식 `lerobot-record`를 안 쓰나

1. 공식 녹화는 카메라를 기본 OpenCV 방식으로 여는데, WSL+usbipd에서는 `Bad file descriptor`로 실패합니다.
   → `usbip_camera.py`의 `UsbipOpenCVCamera`가 카메라를 **MJPG 640x480으로 한 번에** 열어서 해결
   (YUYV 비압축은 usbip 대역폭 초과, 1280x720은 MJPG 협상 실패가 실측됨)
2. usbip로 넘어온 영상에는 아래쪽이 회색으로 깨진 프레임이 섞여 들어옵니다.
   → 압축 원본을 `simplejpeg`로 엄격하게 디코딩해서 깨진 프레임은 버림
3. WSL에서는 Rerun 미리보기 창이 안 뜸 → 브라우저용 MJPEG 미리보기(`MjpegServer`)
4. "손 시연 → 재생" 2단계 흐름이 필요

저장 형식은 공식과 같은 LeRobotDataset v3라서 `lerobot-train`에 그대로 넣을 수 있습니다.

### record_dataset.py 안의 안전장치

| 장치 | 이유 |
|---|---|
| 시작 자세로 부드럽게 이동 (smoothstep, 30도/초) | 갑자기 튀는 동작 방지 |
| 토크 끄기 전 3초 카운트다운 | 팔 받칠 시간 |
| 토크 켜기 직전 목표를 현재 위치로 설정 | 켜는 순간 예전 목표로 튀는 것 방지 |
| 궤적에 프레임당 15도 넘는 점프가 있으면 재생 거부 | 모터 급가속 방지 |
| 0.5초보다 짧은 시연은 버림 | 실수로 Space 두 번 누른 경우 |
| 시간이 걸리는 동작 뒤에는 관절값을 새로 읽음 | 예전에 첫 프레임이 이전 에피소드 끝 위치로 기록되던 버그 수정 |
| 그리퍼는 시연 중에도 힘 유지 + 값 고정 | 이 작업은 그리퍼를 안 씀. 데이터는 6차원 그대로 (나중에 잡기 작업과 같은 형식) |

### 원본(`C:\Users\A\lerobot\`)에서 바뀐 점

- `record_dataset.py`: 로봇 포트·카메라 경로를 코드 수정 없이 `--robot-port`, `--camera` 옵션으로 지정 (기본값은 그대로 `/dev/ttyACM0`, `/dev/video0`)
- `feetech_ping_test.py`: 포트를 인자로 받음 (기본 `/dev/ttyACM0`)
- 새로 추가: `attach_usb.ps1`, `setup_session.sh`, `record_flower_reach.sh`, `calibration/`
- 녹화 로직 자체는 변경 없음 (기존 5 에피소드와 같은 형식으로 저장됨)

---

## 10. 다음 단계: 학습

데이터가 모이면 학습 서버(sior, RTX 5080)에서 SmolVLA를 파인튜닝합니다. 업로드만 되어 있으면 서버가 Hub에서 받아갑니다.

```bash
ssh sior@100.101.102.84 '~/lerobot_flower/start_train.sh'
```

핵심 옵션: `--policy.path=lerobot/smolvla_base` (사전학습 모델에서 시작),
`--rename_map='{"observation.images.front": "observation.images.camera1"}'`
(smolvla_base는 카메라 이름이 camera1~3이라 우리 `front` 카메라를 camera1 자리에 넣음).
에피소드가 늘면 `--steps`도 늘립니다 (5ep 때 3000 step).
