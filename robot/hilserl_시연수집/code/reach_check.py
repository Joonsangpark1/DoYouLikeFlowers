"""게임패드 '못 감'이 많은 원인 확인 (11-22). VLA 도착 자세(trial4 데모 끝)에서 출발해
각 방향으로 끝단을 1 cm씩 옮기며(숙임 고정) teleop_wrist와 같은 IK 판정으로 몇 cm까지 가는지,
막힐 때 어느 관절이 URDF 범위 끝에 걸렸는지 본다. 숙임 고정을 풀면 얼마나 더 가는지도 비교."""
import json, math
from pathlib import Path
import numpy as np
from teleop_wrist import WristIK
from lerobot.datasets.lerobot_dataset import LeRobotDataset

HERE = Path(__file__).resolve().parent
cfg = json.loads((HERE / "configs/flower_hil.json").read_text())
ik_cfg = cfg["env"]["processor"]["inverse_kinematics"]
names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
lo, hi = np.full(6, -180.0), np.full(6, 180.0)
ik = WristIK(str(HERE / ik_cfg["urdf_path"]), ik_cfg["target_frame_name"], names, lo, hi)
for i, n in enumerate(names):
    try:
        jl = ik.kin.robot.get_joint_limits(n); lo[i], hi[i] = math.degrees(jl[0]) + 1, math.degrees(jl[1]) - 1
    except Exception:
        pass
print("URDF 관절 범위(도):", {n: (round(a), round(b)) for n, a, b in zip(names, lo, hi)})

root = Path.home() / "lerobot_data/parkjoonsang/flower_reach_trial4"
ds = LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
A = np.stack(ds.hf_dataset.with_format("numpy")["action"])
to = list(ds.meta.episodes["dataset_to_index"])
import sys
starts = [A[to[e] - 1].astype(float) for e in range(0, ds.num_episodes, 45)]  # 12개 표본
if len(sys.argv) > 1:  # 자세 직접 지정: 관절 6개 쉼표
    starts = [np.array([float(v) for v in a.split(",")]) for a in sys.argv[1:]]
print("VLA 도착 자세 예:", np.round(starts[0], 1), " 숙임", round(ik.pose(starts[0])[1]))

DIRS = {"앞+x": [1, 0, 0], "뒤-x": [-1, 0, 0], "왼+y": [0, 1, 0], "오른-y": [0, -1, 0], "위+z": [0, 0, 1], "아래-z": [0, 0, -1]}
def walk(q0, d, fix_pitch=True, max_cm=15):
    q = q0.copy(); p, pitch = ik.pose(q)
    for k in range(1, max_cm + 1):
        pn = p + np.array(d) * 0.01
        qs, perr, aerr = ik.solve(q, pn, pitch if fix_pitch else ik.pose(q)[1])
        ok = perr < 0.01 and (aerr < 5.0 if fix_pitch else True)
        if not ok:
            at = [names[j] for j in range(4) if qs[j] <= lo[j] + 0.5 or qs[j] >= hi[j] - 0.5]
            return k - 1, at or [f"오차 {perr*100:.1f}cm/{aerr:.0f}°"]
        q, p = qs, pn
    return max_cm, []
for fix in (True, False):
    print(f"\n숙임 {'고정' if fix else '자유'}: 방향별 갈 수 있는 거리 cm (12개 도착 자세 중앙값, 막힌 원인 최다)")
    for dn, d in DIRS.items():
        res = [walk(q, d, fix) for q in starts]
        dist = [r[0] for r in res]; why = {}
        for r in res:
            for w in r[1]: why[w] = why.get(w, 0) + 1
        print(f"  {dn:6s} 중앙 {np.median(dist):4.1f}  최소 {min(dist):2d}  원인 {sorted(why.items(), key=lambda x: -x[1])[:2]}")
