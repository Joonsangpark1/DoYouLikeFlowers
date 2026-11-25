"""HIL prior 시연(flower_hil_prior)을 강화학습 오프라인 데이터셋으로 변환 (11-23).
- 손목 사진 → rl_obs.preprocess_wrist (128x128), 고정 카메라(C270)는 뺌 (옛 구도 + 정책 입력 아님)
- 관절 상태, 행동 [dx,dy,dz,droll,gripper], next.reward, next.done, discrete_penalty 그대로
사용 (서버 sior, conda lerobot):
  SRC=~/lerobot_data/parkjoonsang/flower_hil_prior DST=~/lerobot_data/parkjoonsang/flower_hil_prior_rl128 python build_rl_dataset.py
"""
import os
import shutil
from pathlib import Path

import numpy as np
import torch
from lerobot.datasets.lerobot_dataset import LeRobotDataset

from rl_obs import ACTION_DIM, IMG, STATE_KEY, WRIST_KEY, preprocess_wrist

SRC = Path(os.path.expanduser(os.environ.get("SRC", "~/lerobot_data/parkjoonsang/flower_hil_prior")))
DST = Path(os.path.expanduser(os.environ.get("DST", "~/lerobot_data/parkjoonsang/flower_hil_prior_rl128")))
REPO = os.environ.get("REPO", "parkjoonsang/flower_hil_prior_rl128")

src = LeRobotDataset("parkjoonsang/flower_hil_prior", root=SRC)
feats = {
    STATE_KEY: {"dtype": "float32", "shape": (6,), "names": None},
    WRIST_KEY: {"dtype": "video", "shape": (IMG, IMG, 3), "names": ["height", "width", "channels"]},
    "action": {"dtype": "float32", "shape": (ACTION_DIM,), "names": None},
    "next.reward": {"dtype": "float32", "shape": (1,), "names": None},
    "next.done": {"dtype": "bool", "shape": (1,), "names": None},
    "complementary_info.discrete_penalty": {"dtype": "float32", "shape": (1,), "names": ["discrete_penalty"]},
}
if DST.exists():
    shutil.rmtree(DST)
dst = LeRobotDataset.create(REPO, fps=src.fps, features=feats, root=DST, robot_type="so101_follower",
                            use_videos=True, image_writer_threads=8)
fr, to = list(src.meta.episodes["dataset_from_index"]), list(src.meta.episodes["dataset_to_index"])
for e in range(src.num_episodes):
    for i in range(fr[e], to[e]):
        x = src[i]
        img = (x[WRIST_KEY].permute(1, 2, 0).clamp(0, 1) * 255).round().to(torch.uint8).numpy()
        dst.add_frame({
            STATE_KEY: x[STATE_KEY].numpy().astype(np.float32),
            WRIST_KEY: preprocess_wrist(img),
            "action": x["action"].numpy().astype(np.float32),
            "next.reward": x["next.reward"].numpy().reshape(1).astype(np.float32),
            "next.done": x["next.done"].numpy().reshape(1).astype(bool),
            "complementary_info.discrete_penalty": x["complementary_info.discrete_penalty"].numpy().reshape(1).astype(np.float32),
            "task": x["task"],
        })
    dst.save_episode()
    print(f"ep {e + 1}/{src.num_episodes}", flush=True)
dst.finalize()
print("완료", DST, dst.num_episodes, dst.num_frames)
