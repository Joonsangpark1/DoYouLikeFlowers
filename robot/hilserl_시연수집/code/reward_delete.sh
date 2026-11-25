#!/bin/bash
# 보상 분류기 데이터에서 에피소드 여러 개 지우기 (11-23). 백업 → 임시 폴더에 편집본 → 바꿔치기 → 로그 번호 다시 매김
# 사용: bash reward_delete.sh 1 2 3 9
set -e
cd ~/lerobot_data/parkjoonsang
R=flower_reward
[ $# -gt 0 ] || { echo "지울 에피소드 번호를 주세요"; exit 1; }
if ps -eo args | grep 'record_reward.p[y]' | grep -q python; then echo "녹화 실행 중 -> 먼저 끄기"; exit 1; fi
IDX=$(echo "$@" | tr ' ' ',')
BK=${R}_backup_$(date +%m%d_%H%M%S)
cp -r "$R" "$BK"; cp "${R}_log.jsonl" "${BK}_log.jsonl"
echo "백업: $BK"
TMP="$PWD/${R}_edit_tmp"; rm -rf "$TMP"
~/miniforge3/envs/lerobot/bin/lerobot-edit-dataset --repo_id "parkjoonsang/$R" --root "$PWD/$R" --new_root "$TMP" \
  --operation.type delete_episodes --operation.episode_indices "[$IDX]" 2>&1 | grep -vE 'realsense' | tail -2
[ -f "$TMP/meta/info.json" ] || { echo "편집 실패 (원본 그대로)"; exit 1; }
rm -rf "$R" && mv "$TMP" "$R"
python3 - "$R" "$@" <<'PY'
import json, sys
p = f"{sys.argv[1]}_log.jsonl"; dele = sorted(int(x) for x in sys.argv[2:])
rows = [json.loads(l) for l in open(p) if l.strip()]
keep = []
for r in rows:
    e = r["episode_index"]
    if e in dele:
        continue
    r["episode_index"] = e - sum(1 for d in dele if d < e)
    keep.append(r)
open(p, "w").write("".join(json.dumps(r) + "\n" for r in keep))
pos = sum(r["frames"] for r in keep if r["label"] == 1); neg = sum(r["frames"] for r in keep if r["label"] == 0)
print(f"로그 {len(rows)} -> {len(keep)}구간 | 성공 {pos}장 / 실패 {neg}장")
PY
python3 -c "import json;d=json.load(open('$R/meta/info.json'));print('데이터셋 episodes',d['total_episodes'],'frames',d['total_frames'])"
