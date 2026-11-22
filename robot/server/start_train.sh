#!/bin/bash
# sior에서 학습을 tmux 세션 train으로 실행 (SSH 끊겨도 유지). 인자는 train_smolvla.sh에 그대로 전달
T=~/miniconda3/envs/lerobot/bin/tmux
$T has-session -t train 2>/dev/null && $T kill-session -t train
LOG=~/lerobot_flower/train_$(date +%m%d_%H%M).log
$T new-session -d -s train "source ~/miniconda3/etc/profile.d/conda.sh; conda activate lerobot; cd ~/lerobot; AUG=$AUG P_ORIG=$P_ORIG FLOWER_STATE_NOISE_STD=$STATE_NOISE REPO_ID=$REPO_ID OUT_NAME=$OUT_NAME STEPS=$STEPS BATCH=$BATCH bash ~/lerobot_flower/train_smolvla.sh $* 2>&1 | tee $LOG; exec bash"
echo "학습 시작. 로그: $LOG"
