#!/bin/bash
# HIL-SERL 학습기(learner)를 tmux 세션 learner로 실행 (11-23). gRPC 0.0.0.0:50051, 노트북 flower_actor.py가 접속
# 사용: bash ~/lerobot_flower/rl/start_learner.sh [출력 이름]   (기본 flower_hil_MMDD_HHMM)
T=~/miniconda3/envs/lerobot/bin/tmux
NAME=${1:-flower_hil_$(date +%m%d_%H%M)}
$T has-session -t learner 2>/dev/null && { echo "이미 실행 중 (tmux attach -t learner)"; exit 0; }
LOG=~/lerobot_flower/rl/learner_$NAME.log
$T new-session -d -s learner "source ~/miniconda3/etc/profile.d/conda.sh; conda activate lerobot; cd ~/lerobot; FLOWER_IDLE_S=${FLOWER_IDLE_S:-30} python -m lerobot.rl.learner --config_path ~/lerobot_flower/rl/flower_rl_train.json --output_dir=/home/sior/lerobot/outputs/rl/$NAME --job_name=$NAME 2>&1 | grep --line-buffered -vE 'Svt|SVT|it/s\]' | tee $LOG; exec bash"
echo "learner 시작: $NAME  로그 $LOG"
