#!/bin/bash
# HIL 시연 데이터 현황 (11-22): 폴더·기록·VLA 실패 기록 개수
cd ~/lerobot_data/parkjoonsang || exit 1
ps -eo args | grep record_prior | grep python | grep -v grep && echo "(녹화 프로그램 실행 중)"
ls -d flower_hil* 2>/dev/null || echo "HIL 데이터 없음"
for f in flower_hil*_collection_log.jsonl; do
  [ -f "$f" ] && echo "== $f" && cat "$f"
done
for d in flower_hil*_vla_fail; do
  [ -d "$d" ] && echo "== $d" && cat "$d/log.jsonl" 2>/dev/null && echo "사진 $(ls "$d"/*.jpg 2>/dev/null | wc -l)장"
done
true
