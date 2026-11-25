#!/bin/bash
# HIL-SERL 학습기 이어서 실행 (11-24). checkpoints/last가 가리키는 체크포인트 + 저장된 온라인 버퍼(dataset/)에서 계속
# 사용: bash ~/lerobot_flower/rl/resume_learner.sh flower_hil_1123b
T=~/miniconda3/envs/lerobot/bin/tmux
NAME=${1:?실행 이름 필요 (예 flower_hil_1123b)}
OUT=/home/sior/lerobot/outputs/rl/$NAME
CFG=$OUT/checkpoints/last/pretrained_model/train_config.json
[ -f "$CFG" ] || { echo "체크포인트 설정 없음: $CFG"; exit 1; }
$T has-session -t learner 2>/dev/null && { echo "이미 실행 중 (tmux attach -t learner)"; exit 0; }
LOG=~/lerobot_flower/rl/learner_${NAME}_resume_$(date +%m%d_%H%M).log
$T new-session -d -s learner "source ~/miniconda3/etc/profile.d/conda.sh; conda activate lerobot; cd ~/lerobot; FLOWER_IDLE_S=${FLOWER_IDLE_S:-30} python -m lerobot.rl.learner --config_path $CFG --resume=true 2>&1 | grep --line-buffered -vE 'Svt|SVT|it/s\]' | tee $LOG; exec bash"
echo "learner 이어서 시작: $NAME ($(readlink $OUT/checkpoints/last))  로그 $LOG"
