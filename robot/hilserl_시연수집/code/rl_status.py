"""강화학습 진행 현황 (11-23): flower_rl_episodes.jsonl을 10개씩 요약.
사용: python rl_status.py ["2026-11-24 23:43"]  (이 시각 이후만, 날짜 포함 / 시:분만 주면 날짜 무시)"""
import json, sys
from pathlib import Path
from collections import Counter

rows = [json.loads(l) for l in open(Path.home() / "lerobot_data/parkjoonsang/flower_rl_episodes.jsonl") if l.strip()]
since = sys.argv[1] if len(sys.argv) > 1 else None
if since:
    rows = [r for r in rows if (r["time"] >= since if len(since) > 5 else r["time"][11:16] >= since)]
print(f"에피소드 {len(rows)}개  ({rows[0]['time'] if rows else '-'} ~ {rows[-1]['time'] if rows else '-'})")
print("결과", dict(Counter(r["result"] for r in rows)), " 꽃", dict(Counter(r["flower"] for r in rows)))
k = 10
for i in range(0, len(rows), k):
    g = [r for r in rows[i:i + k] if r["result"] in ("success", "failure", "timeout")]
    if not g:
        continue
    st = sum(r["steps"] for r in g); iv = sum(r["intervention_steps"] for r in g)
    sc = sum(r["result"] == "success" for r in g)
    nofull = sum(r["intervention_steps"] < r["steps"] for r in g)
    print(f"  {i:3d}~{i + len(rows[i:i + k]) - 1:3d}: 성공 {sc}/{len(g)}  개입 비율 {iv / max(st, 1):.0%}  "
          f"정책이 일부라도 직접 움직인 에피소드 {nofull}/{len(g)}  평균 {st / len(g) / 10:.0f}s")
