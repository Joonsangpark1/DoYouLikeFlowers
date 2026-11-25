#!/bin/bash
# HIL prior 데이터셋 마지막 에피소드 확인 (11-23)
cd ~/lerobot_data/parkjoonsang || exit 1
R=${1:-flower_hil_prior}
ps -eo args | grep 'record_prior.p[y]' | grep -q python && echo "녹화 실행 중"
python3 -c "import json;d=json.load(open('$R/meta/info.json'));print('episodes',d['total_episodes'],'frames',d['total_frames'])"
echo "로그 줄 수: $(grep -c . ${R}_collection_log.jsonl)"
tail -2 ${R}_collection_log.jsonl
