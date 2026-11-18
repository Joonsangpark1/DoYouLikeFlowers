#!/bin/bash
# sior에서 추론 서버를 tmux 세션 policy로 띄움. 접속: ~/miniconda3/envs/lerobot/bin/tmux attach -t policy
T=~/miniconda3/envs/lerobot/bin/tmux
$T has-session -t policy 2>/dev/null && { echo "이미 실행 중 (tmux 세션 policy)"; exit 0; }
$T new-session -d -s policy "source ~/miniconda3/etc/profile.d/conda.sh; conda activate lerobot; cd ~/lerobot_flower; python serve_policy.py --host=0.0.0.0 --port=8080 --fps=${FPS:-10} 2>&1 | tee ~/lerobot_flower/serve.log; exec bash"
echo "policy 서버 시작 (포트 8080)"
