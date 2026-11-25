"""보상 분류기 데이터 사진 확인 (11-23): 성공·실패 구간마다 가운데 프레임 1장씩 격자로."""
import json
from pathlib import Path
import cv2, numpy as np
from lerobot.datasets.lerobot_dataset import LeRobotDataset

root = Path.home() / "lerobot_data/parkjoonsang/flower_reward"
ds = LeRobotDataset("parkjoonsang/flower_reward", root=root)
log = [json.loads(l) for l in open(str(root) + "_log.jsonl") if l.strip()]
fr, to = list(ds.meta.episodes["dataset_from_index"]), list(ds.meta.episodes["dataset_to_index"])
tiles = []
for r in log:
    e = r["episode_index"]
    if e >= ds.num_episodes:
        continue
    i = (fr[e] + to[e]) // 2
    img = (ds[i]["observation.images.front"].permute(1, 2, 0).numpy() * 255).astype(np.uint8)[:, :, ::-1].copy()
    img = cv2.resize(img, (320, 240))
    c = (0, 200, 0) if r["label"] == 1 else (0, 0, 255)
    cv2.rectangle(img, (0, 0), (319, 239), c, 6)
    cv2.putText(img, f"ep{e} {'POS' if r['label'] else 'NEG'} {r['frames']}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, c, 2)
    tiles.append(img)
while len(tiles) % 6:
    tiles.append(np.zeros((240, 320, 3), np.uint8))
grid = np.vstack([np.hstack(tiles[k:k + 6]) for k in range(0, len(tiles), 6)])
cv2.imwrite("/mnt/d/data/flower/peek_reward.jpg", grid)
print("saved", len(log))
