#!/bin/bash
# 학습기 현황 (11-25): 실행 여부, 최근 단계, 멈춤 상태, 체크포인트, 저장된 온라인 버퍼
NAME=${1:-flower_hil_1123b}
OUT=~/lerobot/outputs/rl/$NAME
echo "시각 $(date +%m-%d_%H:%M)  학습기 $(pgrep -f lerobot.rl.learner >/dev/null && echo 실행중 || echo 꺼짐)"
f=$(ls -t ~/lerobot_flower/rl/learner_${NAME}*.log 2>/dev/null | head -1)
[ -n "$f" ] && grep -E 'Number of optimization step|pause optim|resume optim' "$f" | tail -2
echo "체크포인트: $(ls $OUT/checkpoints | tail -4 | tr '\n' ' ') (last -> $(readlink $OUT/checkpoints/last))"
python3 -c "import json;d=json.load(open('$OUT/dataset/meta/info.json'));print('저장된 온라인 버퍼', d['total_episodes'], '에피소드', d['total_frames'], '프레임')"
