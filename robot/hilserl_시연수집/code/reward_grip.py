"""보상 데이터 구간별 그리퍼 값·끝단 높이 (11-23): 성공 구간에 그리퍼가 닫혀(줄기를 잡고) 있는지 확인.
그리퍼 0 = 끝까지 열림, 100 = 닫힘."""
import json
from pathlib import Path
import numpy as np
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from teleop_wrist import WristIK

HERE = Path(__file__).resolve().parent
cfg = json.loads((HERE / "configs/flower_hil.json").read_text())["env"]["processor"]["inverse_kinematics"]
names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
ik = WristIK(str(HERE / cfg["urdf_path"]), cfg["target_frame_name"], names, np.full(6, -180.0), np.full(6, 180.0))
root = Path.home() / "lerobot_data/parkjoonsang/flower_reward"
ds = LeRobotDataset("parkjoonsang/flower_reward", root=root)
S = np.stack(ds.hf_dataset.with_format("numpy")["observation.state"])
log = [json.loads(l) for l in open(str(root) + "_log.jsonl") if l.strip()]
fr, to = list(ds.meta.episodes["dataset_from_index"]), list(ds.meta.episodes["dataset_to_index"])
for r in log:
    e = r["episode_index"]
    s = S[fr[e]:to[e]]
    p = np.array([ik.pose(q)[0] for q in s[:: max(1, len(s) // 5)]])
    print(f"ep{e:2d} {'POS' if r['label'] else 'NEG'} {r['frames']:3d}장  그리퍼 {s[:, 5].min():5.1f}~{s[:, 5].max():5.1f}"
          f"  끝단 x {p[:, 0].mean():.2f} y {p[:, 1].mean():+.2f} z {p[:, 2].mean():.2f}")
