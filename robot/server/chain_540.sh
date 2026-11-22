#!/bin/bash
# 11-22: 540ep → hold20 만들고 바로 학습 (snoise2 + aug + 원본20%)
source ~/miniconda3/etc/profile.d/conda.sh; conda activate lerobot; cd ~/lerobot_flower
D=~/lerobot_data/parkjoonsang
SRC=$D/flower_reach_trial4_540 DST=$D/flower_reach_trial4_540_hold20 HOLD=20 python build_hold.py || { echo "HOLD 실패"; exit 1; }
python -c "import json;d=json.load(open('$D/flower_reach_trial4_540_hold20/meta/info.json'));print('hold 완료',d['total_episodes'],d['total_frames'])"
STATE_NOISE=2 AUG=1 P_ORIG=0.2 REPO_ID=parkjoonsang/flower_reach_trial4_hold OUT_NAME=smolvla_trial4_540_hold20_aug_snoise2_$(date +%m%d_%H%M) bash ~/lerobot_flower/start_train.sh $D/flower_reach_trial4_540_hold20
