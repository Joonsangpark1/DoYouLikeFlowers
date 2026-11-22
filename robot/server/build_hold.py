"""trial4 각 에피소드 끝에 '도착 후 정지' 프레임을 덧붙인 새 데이터셋 (11-21).
마지막 프레임의 사진·상태·행동을 HOLD개 그대로 반복 → 학습 때 에피소드 끝 뒤 행동(원래 action_is_pad로 loss 제외)이 '멈춤'으로 들어감.
사용: SRC=... DST=... HOLD=20 [LIMIT=2] python build_hold.py"""
import os, shutil, json, numpy as np, torch
from pathlib import Path
from lerobot.datasets.lerobot_dataset import LeRobotDataset

SRC = Path(os.environ["SRC"]); DST = Path(os.environ["DST"])
HOLD = int(os.environ.get("HOLD", 20)); LIMIT = int(os.environ.get("LIMIT", 0))
src = LeRobotDataset("parkjoonsang/flower_reach_trial4", root=SRC)
AUTO = {"index", "episode_index", "frame_index", "timestamp", "task_index"}
feats = {k: v for k, v in src.meta.features.items() if k not in AUTO}
if DST.exists(): shutil.rmtree(DST)
dst = LeRobotDataset.create("parkjoonsang/flower_reach_trial4_hold", fps=src.fps, features=feats, root=DST,
                            robot_type=src.meta.robot_type, use_videos=True, image_writer_threads=8)
fr, to = list(src.meta.episodes["dataset_from_index"]), list(src.meta.episodes["dataset_to_index"])
n_ep = LIMIT or src.num_episodes
for e in range(n_ep):
    last = None
    for i in range(fr[e], to[e]):
        x = src[i]
        f = {"task": x["task"]}
        for k in feats:
            v = x[k]
            if feats[k]["dtype"] in ("video", "image"):
                v = (v.permute(1, 2, 0).clamp(0, 1) * 255).round().to(torch.uint8).numpy()
            else:
                v = v.numpy()
            f[k] = v
        last = dict(f); dst.add_frame(f)  # add_frame이 task를 빼가므로 먼저 복사
    for _ in range(HOLD):
        dst.add_frame(dict(last))
    dst.save_episode()
    if e % 50 == 0: print("ep", e, flush=True)
dst.finalize()
print("done", dst.num_episodes, dst.num_frames, "src frames", sum(to[e] - fr[e] for e in range(n_ep)))
