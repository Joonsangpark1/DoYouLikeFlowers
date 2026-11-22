"""작업 영역 확인 (11-22): 시작 자세·VLA 도착 자세(trial4 데모 끝)·통 위치를 끝단 좌표로 보고 측정 bounds와 비교."""
import json
from pathlib import Path
import numpy as np
from lerobot.model import RobotKinematics
from lerobot.datasets.lerobot_dataset import LeRobotDataset

HERE = Path(__file__).resolve().parent
cfg = json.loads((HERE / "configs/flower_hil.json").read_text())
ik = cfg["env"]["processor"]["inverse_kinematics"]
M = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
kin = RobotKinematics(str(HERE / ik["urdf_path"]), ik["target_frame_name"], joint_names=M)
fk = lambda q: kin.forward_kinematics(np.asarray(q, float))[:3, 3]
b = ik["end_effector_bounds"]; print("측정 bounds", b)

sp = json.loads(Path("/mnt/c/Users/A/Desktop/로보틱스/smolvla_데이터수집/code/start_pose_vla_trial4.json").read_text())
print("VLA 시작 자세 끝단", np.round(fk([sp[m] for m in M]), 3))

root = Path.home() / "lerobot_data/parkjoonsang/flower_reach_trial4"
ds = LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log = {r["episode_index"]: r for r in map(json.loads, open(str(root) + "_collection_log.jsonl"))}
A = np.stack(ds.hf_dataset.with_format("numpy")["action"])
to = list(ds.meta.episodes["dataset_to_index"])
for s in (1, 2, 3):
    P = np.array([fk(A[to[e] - 1]) for e in range(ds.num_episodes) if log[e]["target_slot"] == s])
    print(f"칸{s} 도착 끝단 min {np.round(P.min(0),3)} max {np.round(P.max(0),3)} 평균 {np.round(P.mean(0),3)}")
