#!/usr/bin/env bash
# flower_reach 녹화 단축 명령.
# 지시문 문장을 여기 고정해둬서 오타 하나로 다른 task가 생기는 사고를 막는다.
#
# 사용:
#   bash record_flower_reach.sh                     # 데이터셋을 처음 만들 때
#   bash record_flower_reach.sh --resume            # 기존 데이터셋에 이어서 (보통 이것)
#   bash record_flower_reach.sh --resume --push private   # 끝낼 때(ESC) Hugging Face에 업로드
#   bash record_flower_reach.sh --resume --camera /dev/video2   # 카메라 번호가 다를 때
#
# 저장 이름은 REPO_ID 환경변수로 바꾼다 (기본 parkjoonsang/flower_reach_trial4):
#   REPO_ID=<내HF아이디>/flower_reach_<이름> bash record_flower_reach.sh
#
# trial4 (2026-11-17~): 처음부터 다시 수집. trial3과 다른 점:
#   - 새 시작 자세 (어깨 들고 손목 덜 숙임 → 카메라가 앞쪽 위를 더 넓게 봄)
#   - 손목 회전 캘리브레이션 기준점 180° 이동 (homing_offset 1528 -> -520, shift_wrist_roll.py):
#     작업 자세가 ±180° 경계(+179°)라 시연 중 넘어가면 시작 자세로 갈 때 한 바퀴 돌던 문제 해결. 이제 약 -1°.
#     → trial3과 손목 회전 숫자 표현이 180° 다름. 섞지 말 것
#   - 카메라는 Windows camera_sender_windows.py → net (30 fps, usbip는 6~7 fps)
#   - 처음부터 섞어서 모음 (--order balanced)
#
# trial3 (2026-11-16~11-17, 183개): 그리퍼 교체 + 그리퍼만 재캘리브레이션 후 수집.
#   꽃병 배치 3개 × 꽃 3종 × 30 = 270. 배치 다 차면 다음 배치로 바꾸라고 알림 → 꽃 바꿔 꽂고 L
#   11-17부터 배치 안에서 꽃을 섞어 모음 (--order balanced: 가장 적게 모인 꽃 추천, 그 번호 키로 지시문 선택).
#   처음 177개는 sequential(rose 30 → blue 30 → sunflower 30)로 모았더니, 모델이 지시문 대신
#   "어느 시간대 장면인지"로 꽃을 맞춤 (오프라인 검증: 지시문 바꾸면 32%만 따름) → 섞어서 지름길을 끊음
#   배치 3개 = 회전 (꽃마다 1·2·3번 칸을 한 번씩):
#     배치1: 1번칸 sunflower / 2번칸 blue      / 3번칸 rose   (11-16 정정: 처음 61개 실제 배치)
#     배치2: 1번칸 blue      / 2번칸 rose      / 3번칸 sunflower
#     배치3: 1번칸 rose      / 2번칸 sunflower / 3번칸 blue
#   trial2(parkjoonsang/flower_reach_trial2)는 옛 그리퍼라 섞지 않는다.
cd "$(dirname "$0")" || exit 1
# usbip 재연결 때마다 /dev/video 번호가 바뀜 (11-16: video0 → video2) → 장치 고정 이름으로 현재 번호를 찾음
# (--camera / --robot-port 를 직접 주면 그 값이 우선)
DEV_OPTS=()
# 카메라: 11-17부터 Windows camera_sender_windows.py가 보내는 사진 (CAMERA_SOURCE=usbip 로 예전 방식)
#   usbip로 넘기면 6~7 fps + 깨진 프레임 (Windows 직접은 30 fps). 카메라는 WSL에 attach하지 말 것
if [ "${CAMERA_SOURCE:-net}" = "net" ]; then
  DEV_OPTS+=(--camera-source net)
else
  CAM=$(ls /dev/v4l/by-id/*Innomaker*-video-index0 2>/dev/null | head -1)
  [ -n "$CAM" ] && DEV_OPTS+=(--camera "$(readlink -f "$CAM")")
fi
PORT=$(ls /dev/serial/by-id/usb-1a86_* 2>/dev/null | head -1)
[ -n "$PORT" ] && DEV_OPTS+=(--robot-port "$(readlink -f "$PORT")")
echo "카메라 ${DEV_OPTS[*]:-기본값}"
# fps 10: WSL usbip로 받는 카메라가 초당 약 11장이 한계 (2026-11-13 측정). HIL-SERL도 10fps
exec python record_dataset.py --repo-id "${REPO_ID:-parkjoonsang/flower_reach_trial4}" --fps 10 \
  --per-layout 90 --order balanced \
  --layouts "sunflower,blue,rose;blue,rose,sunflower;rose,sunflower,blue" \
  --task "Move the gripper close to the pink rose." --flower rose \
  --task "Move the gripper close to the blue flower." --flower blue \
  --task "Move the gripper close to the yellow sunflower." --flower sunflower \
  "${DEV_OPTS[@]}" "$@"
