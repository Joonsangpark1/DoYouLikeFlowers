"""학습된 SmolVLA를 데이터셋 첫 프레임에 넣어서
1) 정답 지시문: 예측한 동작 묶음 vs 실제 시연 궤적 오차
2) 지시문 바꿔치기: 같은 사진에 다른 지시문 -> 예측 끝 자세가 그 꽃의 시연 끝 자세와 가까운지
"""
import sys, json, numpy as np, torch
from collections import defaultdict
from lerobot.datasets import LeRobotDataset
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.policies.factory import make_pre_post_processors

ckpt = sys.argv[1]
ds = LeRobotDataset("parkjoonsang/flower_reach_trial2")
policy = SmolVLAPolicy.from_pretrained(ckpt).to("cuda").eval()
pre, post = make_pre_post_processors(policy.config, pretrained_path=ckpt)
tasks = list(ds.meta.tasks.index)
ep_from = ds.meta.episodes["dataset_from_index"]; ep_to = ds.meta.episodes["dataset_to_index"]
J = ["pan", "lift", "elbow", "wflex", "roll", "grip"]

gt = {}  # ep -> (task, actions[T,6])
for e in range(ds.num_episodes):
    a = torch.stack([ds.hf_dataset[i]["action"] for i in range(ep_from[e], ep_to[e])]).numpy()
    t = ds[ep_from[e]]["task"]
    gt[e] = (t, a)
end_mean = {t: np.mean([a[-1] for (tt, a) in gt.values() if tt == t], 0) for t in tasks}
print("시연 끝 자세 평균(관절 deg):")
for t in tasks: print(f"  {t.split()[-2]:>6}: " + " ".join(f"{J[i]}={v:6.1f}" for i, v in enumerate(end_mean[t])))

@torch.no_grad()
def predict(e, task):
    item = ds[ep_from[e]]
    obs = {"observation.images.camera1": item["observation.images.front"], "observation.state": item["observation.state"], "task": task}
    batch = pre(obs)
    chunk = policy.predict_action_chunk(batch)  # [1,50,6] normalized
    out = post(chunk)
    return out[0].float().cpu().numpy()

torch.manual_seed(0)
errs, end_errs, correct, total = [], [], 0, 0
conf = defaultdict(int)
for e in range(0, ds.num_episodes, 2):
    t, a = gt[e]
    p = predict(e, t)
    n = min(len(a), len(p))
    errs.append(np.abs(p[:n] - a[:n]).mean(0))
    end_errs.append(np.abs(p[n - 1] - a[n - 1]))
    for tq in tasks:  # 지시문 바꿔치기
        pq = predict(e, tq)
        end = pq[n - 1]
        nearest = min(tasks, key=lambda tt: np.abs(end[:5] - end_mean[tt][:5]).mean())
        conf[(tq.split()[-2], nearest.split()[-2])] += 1
        correct += nearest == tq; total += 1
print(f"\n[{ckpt.split('/')[-2]}] 정답 지시문, 궤적 전체 평균 오차(deg): " + " ".join(f"{J[i]}={v:.1f}" for i, v in enumerate(np.mean(errs, 0))))
print("  끝 자세 오차(deg):        " + " ".join(f"{J[i]}={v:.1f}" for i, v in enumerate(np.mean(end_errs, 0))))
print(f"  지시문 바꿔치기: 예측 끝 자세가 그 지시문 꽃 쪽 = {correct}/{total}")
print("  (지시문 -> 가장 가까운 꽃) " + ", ".join(f"{k[0]}->{k[1]}:{v}" for k, v in sorted(conf.items())))
