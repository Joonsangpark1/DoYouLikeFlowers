import os, json, numpy as np
from lerobot.datasets.lerobot_dataset import LeRobotDataset
np.set_printoptions(precision=2, suppress=True, linewidth=200)
root=os.path.expanduser("~/lerobot_data/parkjoonsang/flower_reach_trial4_450")
ds=LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log={r["episode_index"]:r for r in map(json.loads, open(root+"_collection_log.jsonl"))}
S=np.stack(ds.hf_dataset.with_format("numpy")["observation.state"]); fr=list(ds.meta.episodes["dataset_from_index"])
F=S[fr]; lay=np.array(["-".join(log[e]["layout"][k][0].upper() for k in "123") for e in range(len(fr))])
pose=json.load(open("/home/sior/lerobot_flower/start_pose_vla.json")) if os.path.exists("/home/sior/lerobot_flower/start_pose_vla.json") else None
run=np.array([3.84,-84.67,41.49,72.08,-1.98,15.71])  # start_pose_vla_trial4.json
std=F.std(0)
print("전체 첫 상태 std", std)
for L in ["S-B-R","B-R-S","R-S-B","B-S-R","R-B-S"]:
    m=F[lay==L].mean(0); d=np.abs((m-run)/std)
    print(L, m, " 실행자세와 거리(표준화)", round(float(np.sqrt((((m-run)/std)**2).sum())),2))
# 첫 상태만으로 배치 맞추기 (최근접 평균)
cent={L:F[lay==L].mean(0) for L in set(lay)}
pred=[min(cent,key=lambda L: np.linalg.norm((f-cent[L])/std)) for f in F]
print("첫 상태만으로 배치 맞춤", np.mean(np.array(pred)==lay).round(2), "(우연 0.2)")
