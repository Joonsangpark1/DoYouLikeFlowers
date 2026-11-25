#!/bin/bash
# VLA 실패 기록 꽃별 개수 (11-23). 사용: bash vla_fail_count.sh [repo 이름, 기본 flower_hil_prior]
L=~/lerobot_data/parkjoonsang/${1:-flower_hil_prior}_vla_fail/log.jsonl
[ -f "$L" ] || { echo "기록 없음: $L"; exit 0; }
echo "전체 $(grep -c . "$L")개"
python3 - "$L" <<'PY'
import json, sys, collections
c = collections.Counter((r["time"][:10], r["flower"]) for r in map(json.loads, open(sys.argv[1])))
for (d, f), n in sorted(c.items()):
    print(f"  {d} {f:10s} {n}")
PY
