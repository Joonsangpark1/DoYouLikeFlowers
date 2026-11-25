"""HIL prior 데이터 사진 보기 (11-23, 보상 분류기 자르기 범위 정하기): 에피소드 몇 개의 중간/성공 직전/첫 성공/마지막 프레임 격자."""
import json, sys
import numpy as np, cv2, torch
from pathlib import Path
from lerobot.datasets.lerobot_dataset import LeRobotDataset

root = Path.home() / "lerobot_data/parkjoonsang/flower_hil_prior"
ds = LeRobotDataset("parkjoonsang/flower_hil_prior", root=root)
fr, to = list(ds.meta.episodes["dataset_from_index"]), list(ds.meta.episodes["dataset_to_index"])
R = np.array(ds.hf_dataset.with_format("numpy")["next.reward"]).reshape(-1)
CAM = __import__("os").environ.get("CAM", "observation.images.front")
eps = [int(x) for x in sys.argv[1:]] or [0, 10, 20, 30, 44]
rows = []
for e in eps:
    a, b = fr[e], to[e]
    pos = np.where(R[a:b] > 0.5)[0]
    first = a + (pos[0] if len(pos) else b - a - 1)
    picks = [(a + (first - a) // 2, "mid"), (max(a, first - 15), "-1.5s"), (max(a, first - 5), "-0.5s"), (first, "pos0"), (b - 1, "last")]
    tiles = []
    for i, tag in picks:
        x = ds[i][CAM]
        img = (x.permute(1, 2, 0).numpy() * 255).astype(np.uint8)[:, :, ::-1].copy()
        cv2.putText(img, f"ep{e} {tag} r={R[i]:.0f}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        for gx in range(0, 640, 80):
            cv2.line(img, (gx, 0), (gx, 479), (255, 255, 255), 1)
        for gy in range(0, 480, 80):
            cv2.line(img, (0, gy), (639, gy), (255, 255, 255), 1)
        tiles.append(cv2.resize(img, (320, 240)))
    rows.append(np.hstack(tiles))
cv2.imwrite(str(Path.home() / ("lerobot_flower/peek_hil_" + CAM.split(".")[-1] + ".jpg")), np.vstack(rows))
print("ok", len(eps))
