"""trial4 SmolVLA 오프라인 검증 (eval_trial3.py와 같은 기준, 11-18) (배치 반영).

각 에피소드 첫 프레임(같은 사진)에 지시문 3개를 하나씩 넣고 예측한 동작 묶음의 끝 자세가
  - 그 에피소드 배치에서 지시한 꽃의 시연 끝 자세 평균(중심)에 가장 가까운지 (꽃 고르기 정확도)
  - 얼마나 가까운지 (관절 4개 pan/lift/elbow/wflex 거리, 도)
를 본다. 배치마다 꽃 칸이 달라서, 지시문만 외우면 다른 배치에서 틀림 → 화면을 보는지 확인.
추가로 정답 지시문 예측 궤적 vs 실제 시연 궤적 평균 오차.
주의: 학습에 쓴 에피소드로 평가 (따로 떼어 둔 검증 세트 없음).
사용: STATE_MODE=episode|startpose|mean python eval_trial4.py <체크포인트/pretrained_model> [에피소드 간격]
  STATE_MODE (시작 상태 통일, 사진은 항상 그 에피소드 첫 프레임):
    episode   = 그 에피소드 첫 프레임 상태 (eval_trial3과 같음)
    startpose = start_pose_trial4.json (실물에서 토크 켜고 시작 자세에 세운 상태)
    mean      = trial4 전체 첫 프레임 상태 평균
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np
import torch
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

ckpt = sys.argv[1]
stride = int(sys.argv[2]) if len(sys.argv) > 2 else 1
root = os.path.expanduser(os.environ.get("EVAL_ROOT", "~/lerobot_data/parkjoonsang/flower_reach_trial4"))
ds = LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log = {}
for line in open(root + "_collection_log.jsonl"):
    r = json.loads(line)
    log[r["episode_index"]] = r
FLOWERS = ["rose", "blue", "sunflower"]
TASK = {"rose": "Move the gripper close to the pink rose.", "blue": "Move the gripper close to the blue flower.",
        "sunflower": "Move the gripper close to the yellow sunflower."}
policy = SmolVLAPolicy.from_pretrained(ckpt).to("cuda").eval()
pre, post = make_pre_post_processors(policy.config, pretrained_path=ckpt)
e_from, e_to = ds.meta.episodes["dataset_from_index"], ds.meta.episodes["dataset_to_index"]
A = np.stack(ds.hf_dataset.with_format("numpy")["action"])
S0 = np.stack(ds.hf_dataset.with_format("numpy")["observation.state"])[list(e_from)]
MODE = os.environ.get("STATE_MODE", "episode")
_sp = json.load(open(os.path.expanduser("~/lerobot_flower/start_pose_trial4.json")))
FIXED = {"startpose": np.array([_sp[n] for n in ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]], np.float32),
         "mean": S0.mean(0).astype(np.float32)}


def layout_key(e):
    return "/".join(log[e]["layout"][k] for k in "123")


# 배치·꽃별 시연 끝 자세 중심 (관절 4개)
ends = defaultdict(list)
for e in range(ds.num_episodes):
    ends[(layout_key(e), FLOWERS[log[e]["task_index"]])].append(A[e_to[e] - 1][:4])
center = {k: np.mean(v, 0) for k, v in ends.items()}


@torch.no_grad()
def predict(e, task):
    item = ds[e_from[e]]
    obs = {"observation.images.camera1": item["observation.images.front"],
           "observation.state": item["observation.state"] if MODE == "episode" else torch.from_numpy(FIXED[MODE]),
           "task": task}
    return post(policy.predict_action_chunk(pre(obs)))[0].float().cpu().numpy()


torch.manual_seed(0)
res = defaultdict(lambda: [0, 0])  # (layout, 지시 꽃) -> [맞음, 전체]
dist_own, traj_err = [], []
confusion = defaultdict(int)
swap = defaultdict(int)  # 지시문을 바꿨을 때 예측이 간 곳
own = [0, 0]
for e in range(0, ds.num_episodes, stride):
    lay = layout_key(e)
    for f in FLOWERS:
        if (lay, f) not in center:
            continue
        chunk = predict(e, TASK[f])
        true_f = FLOWERS[log[e]["task_index"]]
        T = e_to[e] - e_from[e]
        end = chunk[min(len(chunk), T) - 1][:4]  # 시연 길이만큼 간 시점의 예측 자세
        cands = {g: np.linalg.norm(end - center[(lay, g)]) for g in FLOWERS if (lay, g) in center}
        pick = min(cands, key=cands.get)
        res[(lay, f)][0] += pick == f
        res[(lay, f)][1] += 1
        confusion[(f, pick)] += 1
        if f == true_f:
            own[0] += pick == f
            own[1] += 1
        else:
            swap["지시한 꽃" if pick == f else "원래 에피소드 꽃" if pick == true_f else "나머지 꽃"] += 1
        dist_own.append(cands[f])
        if f == true_f:
            n = min(len(chunk), T)
            traj_err.append(np.abs(chunk[:n, :5] - A[e_from[e]:e_from[e] + n, :5]).mean())

print(f"체크포인트: {ckpt}  (에피소드 {ds.num_episodes}개 중 {stride}개마다)  시작 상태: {MODE}")
tot = [sum(v[0] for v in res.values()), sum(v[1] for v in res.values())]
print(f"\n꽃 고르기 정확도 (같은 사진 + 지시문 3개): {tot[0]}/{tot[1]} = {tot[0] / tot[1]:.0%}")
for (lay, f), (c, n) in sorted(res.items()):
    print(f"  배치 {lay:22s} {f:9s} {c:3d}/{n:3d}  {'' if c == n else '←'}")
print(f"\n정답 지시문(시연과 같은 꽃): {own[0]}/{own[1]} = {own[0] / own[1]:.0%}")
ns = sum(swap.values())
print("바꾼 지시문 → 예측이 간 곳: " + "  ".join(f"{k} {v} ({v / ns:.0%})" for k, v in swap.items()))
print("\n혼동 (지시 → 예측이 가까운 꽃):")
for f in FLOWERS:
    print("  " + f"{f:9s} → " + "  ".join(f"{g} {confusion[(f, g)]}" for g in FLOWERS))
print(f"\n예측 끝 자세 ~ 지시한 꽃의 시연 끝 중심 거리: 평균 {np.mean(dist_own):.1f}° 중앙 {np.median(dist_own):.1f}° (관절 4개 노름)")
print(f"정답 지시문 궤적 오차 (예측 묶음 vs 시연, 관절 5개 평균): {np.mean(traj_err):.1f}°")
cc = {k: v for k, v in center.items()}
gaps = [np.linalg.norm(cc[(l, a)] - cc[(l, b)]) for (l, a) in cc for (l2, b) in cc if l == l2 and a < b]
print(f"참고: 같은 배치 꽃끼리 시연 끝 중심 거리 {np.min(gaps):.1f}~{np.max(gaps):.1f}°")
