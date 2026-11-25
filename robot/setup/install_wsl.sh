#!/usr/bin/env bash
# 꽃꽂이 로봇 WSL(Ubuntu) 환경을 한 번에 설치한다. 여러 번 실행해도 된다 (이미 된 단계는 건너뜀).
# 보통은 Windows에서 install.bat → install_windows.ps1이 이 파일을 대신 불러 준다.
#
# 직접 실행:  bash install_wsl.sh [--hf-user <HF아이디>] [--server <GPU서버주소>] [--yes]
#   --hf-user  데이터셋 저장 이름 앞부분 (~/lerobot_data/<HF아이디>/...). 안 주면 물어봄
#   --server   SmolVLA 추론·강화학습 서버 주소 (예: 100.x.x.x). 데이터 수집만 할 거면 비워도 됨
#   --yes      묻지 않고 기본값으로 진행
#
# 설치하는 것 (원 작성자 노트북과 같은 버전으로 고정):
#   Miniforge(conda) ~/miniforge3 · conda 환경 lerobot(Python 3.12) · ffmpeg 9 (conda-forge)
#   LeRobot 커밋 5aa74557 (~/lerobot) + 우리 수정분 패치 · pip 패키지 버전은 constraints-wsl.txt
#   로봇 캘리브레이션 · 설정 파일 ~/.flower_env
set -eo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROBOT="$(cd "$HERE/.." && pwd)"
LEROBOT_COMMIT=5aa74557
LEROBOT_DIR="$HOME/lerobot"
CONDA_DIR="$HOME/miniforge3"
ENV_NAME=lerobot
PATCH="$ROBOT/server/lerobot_patch/flower_5aa74557.patch"
HF_USER="${FLOWER_HF_USER:-}"; SERVER=""; YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --hf-user) HF_USER="$2"; shift 2 ;;
    --server) SERVER="$2"; shift 2 ;;
    --yes) YES=1; shift ;;
    *) echo "모르는 옵션: $1"; exit 1 ;;
  esac
done

step() { echo; echo "==================== $* ===================="; }
warn() { echo "  ⚠️  $*"; }

step "1/7 Ubuntu 패키지 (sudo 비밀번호를 물어볼 수 있음)"
sudo apt-get update -y
sudo apt-get install -y git curl ca-certificates build-essential usbutils v4l-utils libgl1 libglib2.0-0

step "2/7 Miniforge (conda)"
if [ ! -x "$CONDA_DIR/bin/conda" ]; then
  curl -L -o /tmp/miniforge.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
  bash /tmp/miniforge.sh -b -p "$CONDA_DIR"
  rm -f /tmp/miniforge.sh
else
  echo "  이미 있음: $CONDA_DIR"
fi
# shellcheck disable=SC1091
source "$CONDA_DIR/etc/profile.d/conda.sh"
grep -q "conda initialize" ~/.bashrc || "$CONDA_DIR/bin/conda" init bash >/dev/null

step "3/7 conda 환경 '$ENV_NAME' (Python 3.12 + ffmpeg)"
if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda create -y -n "$ENV_NAME" python=3.12
fi
conda activate "$ENV_NAME"
# LeRobot 영상 저장(SVT-AV1)에 필요. 원 작성자 환경 ffmpeg 9.0.1
ffmpeg -version 2>/dev/null | head -1 | grep -q "version 9" || conda install -y -c conda-forge "ffmpeg=9"

step "4/7 LeRobot $LEROBOT_COMMIT + 수정분 패치"
if [ ! -d "$LEROBOT_DIR/.git" ]; then
  git clone https://github.com/huggingface/lerobot.git "$LEROBOT_DIR"
fi
cd "$LEROBOT_DIR"
if [ "$(git rev-parse --short=8 HEAD)" != "$LEROBOT_COMMIT" ]; then
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    warn "$LEROBOT_DIR 에 고친 파일이 있어서 커밋을 바꾸지 않습니다. 직접 확인하세요 (git status)."
  else
    git fetch origin && git checkout "$LEROBOT_COMMIT"
  fi
fi
if git apply --check "$PATCH" 2>/dev/null; then
  git apply "$PATCH" && echo "  패치 적용"
elif git apply -R --check "$PATCH" 2>/dev/null; then
  echo "  패치 이미 적용됨"
else
  warn "패치가 깔끔하게 안 맞습니다 (LeRobot 파일이 이미 다르게 바뀜). 수집에는 영향 없음, 서버 학습만 차이"
fi
# feetech = 로봇 모터, smolvla = VLA, async = 서버 추론 클라이언트(grpc), hilserl = 강화학습(placo 역기구학 포함)
pip install -c "$HERE/constraints-wsl.txt" -e ".[feetech,smolvla,async,hilserl]"
pip install -c "$HERE/constraints-wsl.txt" -r "$HERE/requirements-wsl.txt"

step "5/7 로봇 캘리브레이션"
CALIB_SRC="$ROBOT/smolvla_데이터수집/code/calibration/my_follower_arm.json"
CALIB_DIR="${HF_LEROBOT_CALIBRATION:-${HF_LEROBOT_HOME:-$HOME/.cache/huggingface/lerobot}/calibration}/robots/so_follower"
mkdir -p "$CALIB_DIR"
if [ ! -f "$CALIB_DIR/my_follower_arm.json" ]; then
  cp "$CALIB_SRC" "$CALIB_DIR/my_follower_arm.json" && echo "  공용 캘리브레이션 설치 (원 작성자 로봇 기준)"
elif cmp -s "$CALIB_SRC" "$CALIB_DIR/my_follower_arm.json"; then
  echo "  공용 파일과 같음"
else
  warn "이미 다른 캘리브레이션이 있어서 그대로 둡니다: $CALIB_DIR/my_follower_arm.json"
fi
echo "  ※ 원 작성자 로봇이 아니면 자기 로봇으로 다시 잡을 것 (robot/README.md 3-4)"

step "6/7 설정 파일 ~/.flower_env"
if [ -z "$HF_USER" ] && [ "$YES" = 0 ]; then
  read -r -p "  Hugging Face 아이디 (데이터셋 이름 앞부분, 없으면 Enter = local): " HF_USER
fi
HF_USER="${HF_USER:-local}"
if [ -z "$SERVER" ] && [ -f ~/.flower_env ]; then
  SERVER="$(grep -oP '^export LEARNER=\K.*' ~/.flower_env || true)"
fi
if [ -z "$SERVER" ] && [ "$YES" = 0 ]; then
  read -r -p "  GPU 서버 주소 (SmolVLA 추론·강화학습용, 수집만 하면 Enter): " SERVER
fi
cat > ~/.flower_env <<EOF
# 꽃꽂이 로봇 설정 (install_wsl.sh가 만듦, 고쳐도 됨). 새 터미널부터 적용
export FLOWER_ROBOT_DIR="$ROBOT"
export FLOWER_HF_USER=$HF_USER
export LEARNER=${SERVER:-127.0.0.1}
export FLOWER_SERVER=${SERVER:-127.0.0.1}:8080
EOF
grep -q "flower_env" ~/.bashrc || cat >> ~/.bashrc <<'EOF'
# 꽃꽂이 로봇
[ -f ~/.flower_env ] && source ~/.flower_env
conda activate lerobot 2>/dev/null
EOF
echo "  저장: ~/.flower_env (HF 아이디 $HF_USER, 서버 ${SERVER:-없음})"
# shellcheck disable=SC1090
source ~/.flower_env

step "7/7 점검"
bash "$HERE/doctor.sh" || true
echo
echo "설치 끝. 새 Ubuntu 터미널을 열면 conda 환경과 설정이 자동으로 켜집니다."
echo "데이터를 Hugging Face에 올릴 거면 한 번:  hf auth login"
