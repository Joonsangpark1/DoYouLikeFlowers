source ~/miniconda3/etc/profile.d/conda.sh; conda activate lerobot; cd ~/lerobot_flower
O=~/lerobot/outputs/train
NEW=$O/smolvla_trial4_540_hold20_aug_snoise2_1122_1802/checkpoints/last/pretrained_model
OLD=$O/smolvla_trial4_450_hold20_aug_snoise2_1122_1511/checkpoints/last/pretrained_model
echo "=== realframes"; python eval_realframes_1121.py $OLD $NEW 2>&1 | grep -v Warn
echo "=== st_swap NEW"; python st_swap.py $NEW 2>&1 | grep -E "사진|상태="
for m in NEW OLD; do echo "##### train-frames $m"; EVAL_ROOT=~/lerobot_data/parkjoonsang/flower_reach_trial4_540 STATE_MODE=mean python eval_trial4.py ${!m} 3 2>&1 | grep -vE "Warn|INFO"; done
