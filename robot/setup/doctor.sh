#!/usr/bin/env bash
# 설치·연결 상태 점검 (WSL). 문제가 생기면 먼저 이것부터:  bash doctor.sh
HERE="$(cd "$(dirname "$0")" && pwd)"
ok() { echo "  ✅ $*"; }
bad() { echo "  ❌ $*"; FAIL=1; }
note() { echo "  ⚠️  $*"; }
FAIL=0
[ -f ~/.flower_env ] && source ~/.flower_env
if [ -f ~/miniforge3/etc/profile.d/conda.sh ]; then
  source ~/miniforge3/etc/profile.d/conda.sh; conda activate lerobot 2>/dev/null
fi

echo "== 파이썬 환경 =="
PY="$(command -v python)"
[[ "$PY" == *"/envs/lerobot/"* ]] && ok "conda 환경 lerobot ($PY)" || bad "conda 환경 lerobot이 아님: $PY  → install_wsl.sh 다시 실행"
python - <<'EOF' 2>/dev/null || echo "  ❌ 파이썬 패키지 확인 실패 → install_wsl.sh 다시 실행"
import importlib
for m in ["lerobot", "torch", "cv2", "numpy", "simplejpeg", "placo", "grpc", "scservo_sdk", "transformers"]:
    try:
        mod = importlib.import_module(m); print(f"  ✅ {m} {getattr(mod, '__version__', '')}")
    except Exception as e:
        print(f"  ❌ {m}: {e}")
EOF
if [ -d ~/lerobot/.git ]; then
  c=$(git -C ~/lerobot rev-parse --short=8 HEAD); [ "$c" = 5aa74557 ] && ok "LeRobot 커밋 $c" || note "LeRobot 커밋 $c (기준 5aa74557)"
fi
ffmpeg -version 2>/dev/null | head -1 | grep -q "version" && ok "$(ffmpeg -version | head -1 | cut -c1-30)" || bad "ffmpeg 없음"

echo "== 설정 =="
[ -f ~/.flower_env ] && ok "~/.flower_env (HF 아이디 ${FLOWER_HF_USER:-?}, 서버 ${FLOWER_SERVER:-?})" || bad "~/.flower_env 없음 → install_wsl.sh"
CAL="${HF_LEROBOT_HOME:-$HOME/.cache/huggingface/lerobot}/calibration/robots/so_follower/my_follower_arm.json"
[ -f "$CAL" ] && ok "캘리브레이션 $CAL" || bad "캘리브레이션 없음 → bash setup_session.sh (수집 폴더)"
hf auth whoami >/dev/null 2>&1 && ok "Hugging Face 로그인: $(hf auth whoami 2>/dev/null | head -1)" || note "Hugging Face 로그인 안 됨 (업로드할 때만 필요: hf auth login)"

echo "== 장치 (Windows에서 start_session.ps1 실행 뒤) =="
ls /dev/ttyACM* >/dev/null 2>&1 && ok "로봇 포트 $(ls /dev/ttyACM* | tr '\n' ' ')" || note "로봇 포트 없음 (/dev/ttyACM*) → Windows에서 start_session.ps1"
[ -e /dev/ttyACM0 ] && { [ -r /dev/ttyACM0 ] && [ -w /dev/ttyACM0 ] && ok "로봇 포트 권한" || note "권한 없음 → bash setup_session.sh (sudo chmod)"; }

echo "== GPU 서버 (SmolVLA 추론 8080 / 강화학습 50051) =="
if [ -n "${LEARNER:-}" ] && [ "$LEARNER" != 127.0.0.1 ]; then
  for p in 8080 50051; do
    timeout 2 bash -c "</dev/tcp/$LEARNER/$p" 2>/dev/null && ok "$LEARNER:$p 열림" || note "$LEARNER:$p 응답 없음 (서버가 꺼져 있거나 Tailscale 미연결)"
  done
else
  note "서버 주소 없음 (데이터 수집만 하면 괜찮음. 쓰려면 ~/.flower_env 의 LEARNER/FLOWER_SERVER 수정)"
fi
echo
[ "$FAIL" = 0 ] && echo "점검 끝: 필수 항목 OK" || { echo "점검 끝: ❌ 항목을 먼저 해결하세요"; exit 1; }
