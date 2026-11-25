#!/bin/bash
# 11-25 이상치 제거 비교: A(결함6) / A90(+ep90) / AB(+11-18 R-S-B 36개) / CTRL(제거 없음, 같은 설정 재학습 = 실행간 편차)
source ~/miniconda3/etc/profile.d/conda.sh; conda activate lerobot; cd ~/lerobot_flower
D=~/lerobot_data/parkjoonsang; SRC=$D/flower_reach_trial4_540
A="0,10,175,219,384,451"; A90="$A,90"; AB="$A90,$(seq -s, 234 269)"
declare -A EX=([A]="$A" [A90]="$A90" [AB]="$AB")
for k in A A90 AB; do
  SRC=$SRC DST=$D/flower_reach_trial4_540clean${k}_hold20 HOLD=20 EXCLUDE="${EX[$k]}" python build_hold_excl.py > clean_build_$k.log 2>&1 &
done
wait
for k in A A90 AB; do echo "build $k: $(tail -n1 clean_build_$k.log)"; done
cd ~/lerobot
for k in A A90 AB CTRL; do
  if [ "$k" = CTRL ]; then DS=$D/flower_reach_trial4_540_hold20; else DS=$D/flower_reach_trial4_540clean${k}_hold20; fi
  [ -f "$DS/meta/info.json" ] || { echo "NO_DATASET $k $DS"; continue; }
  echo "=== train $k start $(date +%H:%M)"
  AUG=1 P_ORIG=0.2 FLOWER_STATE_NOISE_STD=2 REPO_ID=parkjoonsang/flower_reach_trial4_hold OUT_NAME=smolvla_540clean${k}_hold20_aug_snoise2_1125 \
    bash ~/lerobot_flower/train_smolvla.sh "$DS" > ~/lerobot_flower/train_clean${k}_1125.log 2>&1 && echo "TRAIN_OK $k $(date +%H:%M)" || echo "TRAIN_FAIL $k"
done
echo ALL_DONE $(date +%H:%M)
