#!/usr/bin/env bash
# 매 세션 시작할 때 WSL(Ubuntu)에서 1번 실행한다. (Windows에서 attach_usb.ps1 먼저)
#   1) 로봇/카메라 장치가 WSL에 보이는지 확인
#   2) 장치 권한 열기 (usbipd로 붙일 때마다 초기화되므로 매번 필요)
#   3) 로봇 캘리브레이션 파일이 없으면 이 폴더의 공용 파일을 설치
#   4) 장치 번호가 config 기본값(/dev/ttyACM0, /dev/video0)과 다르면 알려줌
# 사용: bash setup_session.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
CALIB_SRC="$HERE/calibration/my_follower_arm.json"
CALIB_DIR="${HF_LEROBOT_CALIBRATION:-${HF_LEROBOT_HOME:-$HOME/.cache/huggingface/lerobot}/calibration}/robots/so_follower"
CALIB_DST="$CALIB_DIR/my_follower_arm.json"
ok=1

echo "== 1. 로봇 (USB-시리얼) =="
robots=(/dev/ttyACM*)
if [ ! -e "${robots[0]}" ]; then
  echo "  ❌ /dev/ttyACM* 없음 -> Windows에서 attach_usb.ps1을 먼저 실행하세요"
  ok=0
  robot=""
else
  robot="${robots[0]}"
  echo "  ✅ ${robots[*]}"
fi

echo "== 2. 카메라 =="
# 웹캠 하나가 /dev/video0, /dev/video1 두 개로 보이는데 영상이 나오는 건 index 0인 쪽 (나머지는 메타데이터용)
camera=""
for d in /sys/class/video4linux/video*; do
  [ -e "$d" ] || continue
  if [ "$(cat "$d/index" 2>/dev/null)" = "0" ]; then
    dev="/dev/$(basename "$d")"
    echo "  ✅ $dev  ($(cat "$d/name" 2>/dev/null))"
    [ -z "$camera" ] && camera="$dev"
  fi
done
if [ -z "$camera" ]; then
  echo "  ❌ 카메라 없음 -> Windows에서 attach_usb.ps1을 먼저 실행하세요"
  ok=0
fi

echo "== 3. 장치 권한 열기 (sudo 비밀번호를 물어볼 수 있음) =="
devs=$(ls /dev/ttyACM* /dev/video* 2>/dev/null)
if [ -n "$devs" ]; then
  # shellcheck disable=SC2086
  sudo chmod 666 $devs && echo "  ✅ chmod 666 완료"
fi

echo "== 4. 로봇 캘리브레이션 파일 =="
if [ ! -f "$CALIB_DST" ]; then
  mkdir -p "$CALIB_DIR" && cp "$CALIB_SRC" "$CALIB_DST"
  echo "  ✅ 공용 캘리브레이션 설치 -> $CALIB_DST"
elif cmp -s "$CALIB_SRC" "$CALIB_DST"; then
  echo "  ✅ 공용 파일과 같음"
else
  echo "  ⚠️ $CALIB_DST 가 공용 파일과 다릅니다."
  echo "     다른 사람과 데이터를 합칠 거라면 관절 각도 기준이 달라지므로 공용 파일로 덮어쓰세요:"
  echo "     cp \"$CALIB_SRC\" \"$CALIB_DST\""
fi

echo
if [ "$ok" = 1 ]; then
  echo "준비 완료."
  if [ "$robot" != "/dev/ttyACM0" ] || [ "$camera" != "/dev/video0" ]; then
    echo "⚠️ 장치 번호가 기본값과 다릅니다. configs/*.json 에서 고치세요:"
    echo "   \"port\": \"$robot\"   /   \"index_or_path\": \"$camera\""
  fi
  echo "다음: Windows에서 gamepad_sender.ps1 실행 → python gamepad_test.py 로 게임패드 확인"
else
  echo "❌ 위 문제를 먼저 해결하세요 (README '문제 해결' 참고)"
  exit 1
fi
