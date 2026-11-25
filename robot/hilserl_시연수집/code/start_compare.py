"""VLA 학습 데이터(trial4) 시작 화면 vs 지금 손목 화면 비교 (11-24). 배치 S-R-B 첫 프레임 3장 + 지금 화면."""
import json
from pathlib import Path
import cv2, numpy as np
from lerobot.datasets.lerobot_dataset import LeRobotDataset

root = Path.home() / "lerobot_data/parkjoonsang/flower_reach_trial4"
ds = LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log = {r["episode_index"]: r for r in map(json.loads, open(str(root) + "_collection_log.jsonl"))}
fr = list(ds.meta.episodes["dataset_from_index"])
eps = [e for e in range(ds.num_episodes) if [log[e]["layout"][k] for k in ("1", "2", "3")] == ["sunflower", "rose", "blue"]]
tiles = []
for e in eps[:: max(1, len(eps) // 3)][:3]:
    x = ds[fr[e]]["observation.images.front"]
    img = (x.permute(1, 2, 0).numpy() * 255).astype(np.uint8)[:, :, ::-1].copy()
    cv2.putText(img, f"train ep{e} S-R-B start", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    tiles.append(cv2.resize(img, (480, 360)))
now = cv2.imread("/mnt/d/data/flower/actor_now2.jpg")[34:, :640]
cv2.putText(now, "NOW (RL READY)", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
tiles.append(cv2.resize(now, (480, 360)))
cv2.imwrite("/mnt/d/data/flower/start_compare.jpg", np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:4])]))
print("ok", len(eps))
