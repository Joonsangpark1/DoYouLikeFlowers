#!/bin/bash
# flower_actor.py 자동 재시작 (11-23). 독이 끊겨 에러로 꺼지면 로봇이 다시 붙을 때까지 기다렸다 다시 켬.
# 학습기(sior)는 계속 돌고 있으므로 실행기만 다시 붙으면 학습은 이어짐. 진행 중이던 에피소드 1개만 사라짐.
# SELECT(정상 종료)나 Ctrl+C면 끝. 같은 에러가 20번 연속이면 멈춤.
# 사용 (conda activate lerobot): bash flower_actor_loop.sh
cd "$(dirname "$0")" || exit 1
for try in $(seq 1 20); do
  echo "=== 강화학습 실행기 시작 (${try}번째)"
  python flower_actor.py
  rc=$?   # 0 = SELECT/Ctrl+C 정상 종료, 그 외(2 = 실행기 에러) = 다시 시작
  [ $rc -eq 0 ] && { echo "=== 정상 종료"; exit 0; }
  echo "=== 에러로 꺼짐. 로봇·카메라 다시 붙기를 기다림 (Windows dock_watch.ps1이 재연결)"
  sleep 5
  until ls /dev/serial/by-id/usb-1a86_* >/dev/null 2>&1; do sleep 2; done
  sleep 10
done
echo "=== 20번 연속 에러. 멈춤"
exit 1
