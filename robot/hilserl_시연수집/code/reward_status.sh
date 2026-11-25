#!/bin/bash
# 보상 분류기 데이터 현황 (11-23)
L=~/lerobot_data/parkjoonsang/flower_reward_log.jsonl
ps -eo args | grep 'record_reward.p[y]' | grep -q python && echo "(녹화 실행 중)"
[ -f "$L" ] || { echo "기록 없음"; exit 0; }
python3 - "$L" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
pos = [r for r in rows if r["label"] == 1]; neg = [r for r in rows if r["label"] == 0]
print(f"구간 {len(rows)}개 | 성공 {len(pos)}구간 {sum(r['frames'] for r in pos)}장 | 실패 {len(neg)}구간 {sum(r['frames'] for r in neg)}장")
print("처음", rows[0]["time"] if rows else "-", " 마지막", rows[-1]["time"] if rows else "-")
PY
