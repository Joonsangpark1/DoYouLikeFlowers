#!/bin/bash
# record_prior.py 자동 재시작 (11-23). 독이 끊겨 녹화가 에러(Input/output error 등)로 꺼지면
# 로봇이 다시 붙을 때까지 기다렸다가 이어서(--resume) 다시 켬. 저장된 에피소드는 그대로, 녹화 중이던 1개만 사라짐.
# 정상 종료(SELECT, 목표 개수 채움, Ctrl+C)면 끝. 같은 에러가 계속되면 20번 뒤 멈춤.
# 사용 (conda activate lerobot 상태):
#   bash record_prior_loop.sh --repo-id parkjoonsang/flower_hil_prior --num-episodes 30 --layout "sunflower,rose,blue"
cd "$(dirname "$0")" || exit 1
REPO=""
prev=""
for a in "$@"; do
  [ "$prev" = "--repo-id" ] && REPO="$a"
  prev="$a"
done
[ -n "$REPO" ] || REPO="${FLOWER_HF_USER:-parkjoonsang}/flower_hil_prior"
ROOT="$HOME/lerobot_data/$REPO"

for try in $(seq 1 20); do
  RES=()
  ls "$ROOT"/data/*/*.parquet >/dev/null 2>&1 && RES=(--resume)  # 저장된 에피소드가 있으면 이어서
  echo "=== 녹화 시작 (${try}번째) ${RES[*]}"
  python record_prior.py "$@" "${RES[@]}"
  rc=$?
  [ $rc -eq 0 ] && { echo "=== 정상 종료"; exit 0; }
  echo "=== 에러로 꺼짐 (rc=$rc). 로봇·카메라 다시 붙기를 기다림 (Windows dock_watch.ps1이 재연결)"
  sleep 5
  until ls /dev/serial/by-id/usb-1a86_* >/dev/null 2>&1; do sleep 2; done
  sleep 10  # 송신기(손목·C270·게임패드) 다시 켜질 시간
done
echo "=== 20번 연속 에러. 멈춤 (원인 확인 필요)"
exit 1
