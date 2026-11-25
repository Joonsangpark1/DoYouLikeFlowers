#!/bin/bash
# lerobot-edit-dataset이 ~/.cache/huggingface/lerobot/<repo>에 만든 결과를 원래 자리로 옮김 (11-23)
set -e
cd ~/lerobot_data/parkjoonsang
R=${1:-flower_hil_prior}
NEW=~/.cache/huggingface/lerobot/parkjoonsang/$R
[ -f "$NEW/meta/info.json" ] || { echo "편집 결과 없음: $NEW"; exit 1; }
python3 -c "import json;d=json.load(open('$NEW/meta/info.json'));print('편집본 episodes',d['total_episodes'],'frames',d['total_frames'])"
ls -d ${R}_backup_del* | tail -1
rm -rf "$R"
mv "$NEW" "$R"
python3 -c "import json;d=json.load(open('$R/meta/info.json'));print('지금 episodes',d['total_episodes'],'frames',d['total_frames'])"
echo "로그 줄 수: $(grep -c . ${R}_collection_log.jsonl)"
ls $R/data/*/ $R/videos/*/*/ 2>/dev/null | head -8
