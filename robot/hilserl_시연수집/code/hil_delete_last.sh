#!/bin/bash
# HIL prior 데이터셋에서 마지막 에피소드 1개 지우기 (11-23). 백업 후 삭제, 수집 로그 마지막 줄도 같이.
set -e
cd ~/lerobot_data/parkjoonsang
R=${1:-flower_hil_prior}
if ps -eo args | grep 'record_prior.p[y]' | grep -q python; then echo "녹화 실행 중 -> 먼저 끄기"; exit 1; fi
N=$(python3 -c "import json;print(json.load(open('$R/meta/info.json'))['total_episodes'])")
LAST=$((N - 1))
TS=$(date +%m%d_%H%M%S)
BK=${R}_backup_del${LAST}_$TS
cp -r "$R" "$BK"
cp "${R}_collection_log.jsonl" "${BK}_collection_log.jsonl"
echo "백업: $BK  (지울 에피소드 $LAST / 전체 $N)"
# 결과는 임시 폴더에 만들고(지정 안 하면 ~/.cache/huggingface/lerobot에 생김, 11-23 실제 발생) 원래 자리와 바꿈
TMP="$PWD/${R}_edit_tmp"; rm -rf "$TMP"
~/miniforge3/envs/lerobot/bin/lerobot-edit-dataset --repo_id "parkjoonsang/$R" --root "$PWD/$R" --new_root "$TMP" \
  --operation.type delete_episodes --operation.episode_indices "[$LAST]" 2>&1 | grep -vE 'realsense' | tail -3
[ -f "$TMP/meta/info.json" ] || { echo "편집 실패 (원본 그대로, 백업 $BK)"; exit 1; }
rm -rf "$R" && mv "$TMP" "$R"
# 로그에서 해당 에피소드 줄 빼기
python3 - "$R" "$LAST" <<'PY'
import json, sys
p = f"{sys.argv[1]}_collection_log.jsonl"; last = int(sys.argv[2])
rows = [json.loads(l) for l in open(p) if l.strip()]
keep = [r for r in rows if r["episode_index"] != last]
open(p, "w").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
print(f"로그 {len(rows)} -> {len(keep)}줄")
PY
python3 -c "import json;d=json.load(open('$R/meta/info.json'));print('지금 episodes',d['total_episodes'],'frames',d['total_frames'])"
