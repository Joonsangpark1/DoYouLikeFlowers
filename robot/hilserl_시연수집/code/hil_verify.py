"""HIL prior 데이터셋이 열리고 로그와 맞는지 확인 (11-23)."""
import json
from pathlib import Path
from lerobot.datasets.lerobot_dataset import LeRobotDataset

root = Path.home() / "lerobot_data/parkjoonsang/flower_hil_prior"
ds = LeRobotDataset("parkjoonsang/flower_hil_prior", root=root)
log = [json.loads(l) for l in open(str(root) + "_collection_log.jsonl") if l.strip()]
print("에피소드", ds.num_episodes, "프레임", ds.num_frames, "로그", len(log))
last = ds[ds.num_frames - 1]
print("마지막 프레임 episode_index", int(last["episode_index"]), "reward", float(last["next.reward"]), "done", bool(last["next.done"]))
print("로그 마지막", log[-1]["episode_index"], log[-1]["flower"], log[-1]["result"])
from collections import Counter
print("꽃별", dict(Counter((r["flower"], r["result"]) for r in log)))
