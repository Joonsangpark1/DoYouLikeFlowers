#!/bin/bash
# SmolVLA 파인튜닝. sior(RTX 5080)용. 보통 start_train.sh로 tmux에서 실행.
# 사용: REPO_ID=... OUT_NAME=... STEPS=... BATCH=... bash train_smolvla.sh [로컬 데이터셋 폴더]
#   기본값: parkjoonsang/flower_reach_trial2 (Hub, 비공개 -> hf auth login 필요), batch 32, 10000 step
# 이전 버전(11-09, flower_reach 5ep, batch 8, 3000 step): train_smolvla.sh.bak_1109
set -e

REPO_ID="${REPO_ID:-parkjoonsang/flower_reach_trial2}"
OUT_NAME="${OUT_NAME:-smolvla_trial2_$(date +%m%d_%H%M)}"
STEPS="${STEPS:-10000}"
BATCH="${BATCH:-32}"
SAVE_FREQ="${SAVE_FREQ:-2000}"
OUT_DIR="outputs/train/$OUT_NAME"

# AUG=1: 학습 중 이미지 증강 (11-21). P_ORIG(기본 0.2, 11-22~): 이 확률로 원본 그대로 (lerobot transforms.py 패치, 백업 ~/lerobot_flower/transforms.py.bak_1122). 색/밝기/선명도/살짝 회전·이동 + 사진 일부 지우기(CoarseDropout), 종류는 aug_tfs.json
AUG_ARG=()
if [ "${AUG:-0}" = "1" ]; then
  AUG_ARG=(--dataset.image_transforms.enable=true --dataset.image_transforms.max_num_transforms=3 --dataset.image_transforms.p_original=${P_ORIG:-0.2}
           "--dataset.image_transforms.tfs=$(cat ~/lerobot_flower/aug_tfs.json)")
fi

ROOT_ARG=()
if [ -n "$1" ]; then
  if [ ! -f "$1/meta/info.json" ]; then
    echo "데이터셋이 없음: $1"
    exit 1
  fi
  ROOT_ARG=(--dataset.root="$1")
fi

echo "증강: ${AUG:-0}  원본비율: ${P_ORIG:-0.2}  상태노이즈(도): ${FLOWER_STATE_NOISE_STD:-0}"
echo "데이터: $REPO_ID  출력: $OUT_DIR  steps=$STEPS batch=$BATCH"
# - smolvla_base는 카메라 키가 camera1~3이라 front 카메라를 camera1로 매핑
# - 5080 16GB: batch 8에서 2.4GB 사용(11-09) -> batch 32 여유 있음 (추론 서버가 3GB 쓰는 중이어도 OK)
lerobot-train \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id="$REPO_ID" \
  "${ROOT_ARG[@]}"   "${AUG_ARG[@]}" \
  '--rename_map={"observation.images.front": "observation.images.camera1"}' \
  --batch_size="$BATCH" \
  --steps="$STEPS" \
  --save_freq="$SAVE_FREQ" \
  --log_freq=100 \
  --output_dir="$OUT_DIR" \
  --job_name="$OUT_NAME" \
  --policy.device=cuda \
  --policy.push_to_hub=false \
  --wandb.enable=false
