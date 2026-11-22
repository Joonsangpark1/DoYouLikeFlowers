"""실물 실행 첫 사진(학습에 없던 배치)으로 지시문 3개 예측 → 끝 자세가 어느 칸인지 (11-18).
사용: python eval_realframes.py <pretrained_model> [<pretrained_model> ...]
칸 중심 = trial4 시연 끝 자세(관절 4개)의 칸별 평균, 시작 상태 = trial4 첫 프레임 평균."""
import json, os, sys, glob
import numpy as np, torch, cv2
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.policies.factory import make_pre_post_processors

root = os.path.expanduser("~/lerobot_data/parkjoonsang/flower_reach_trial4_450")
ds = LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log = {r["episode_index"]: r for r in map(json.loads, open(root + "_collection_log.jsonl"))}
e_from, e_to = list(ds.meta.episodes["dataset_from_index"]), list(ds.meta.episodes["dataset_to_index"])
A = np.stack(ds.hf_dataset.with_format("numpy")["action"])
S = np.stack(ds.hf_dataset.with_format("numpy")["observation.state"])
mean0 = torch.from_numpy(S[e_from].mean(0).astype(np.float32))
slot_c = {s: np.mean([A[e_to[e] - 1][:4] for e in range(ds.num_episodes) if log[e]["target_slot"] == s], 0) for s in (1, 2, 3)}
TASK = {"rose": "Move the gripper close to the pink rose.", "blue": "Move the gripper close to the blue flower.",
        "sunflower": "Move the gripper close to the yellow sunflower."}
# 카메라 왼쪽 = 1번 칸 (학습 영상으로 확인)
LAYOUT = {k: "rose,blue,sunflower" for k in ["1121_230141","1121_230242","1121_230337","1121_230508","1121_230610","1121_230658","1121_230745"]}; LAYOUT["1121_230848"] = "sunflower,blue,rose"; LAYOUT["1121_230956"] = "blue,sunflower,rose"; LAYOUT["1122_150640"] = "blue,sunflower,rose"; LAYOUT["1122_161618"] = LAYOUT["1122_161741"] = "blue,sunflower,rose"; LAYOUT["1122_162022"] = LAYOUT["1122_162113"] = "sunflower,rose,blue"
imgs = sorted(glob.glob(os.path.expanduser("~/lerobot_flower/realframes_1121/*.jpg")))
for ckpt in sys.argv[1:]:
    policy = SmolVLAPolicy.from_pretrained(ckpt).to("cuda").eval()
    pre, post = make_pre_post_processors(policy.config, pretrained_path=ckpt)
    torch.manual_seed(0)
    ok = tot = 0
    print(f"\n== {ckpt}")
    for p in imgs:
        name = os.path.basename(p)[:11]
        lay = LAYOUT[name].split(",")
        im = torch.from_numpy(cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float() / 255
        row = []
        for f in TASK:
            with torch.no_grad():
                ch = post(policy.predict_action_chunk(pre({"observation.images.camera1": im, "observation.state": mean0, "task": TASK[f]})))[0].float().cpu().numpy()
            end = ch[-1][:4]
            slot = min(slot_c, key=lambda s: np.linalg.norm(end - slot_c[s]))
            got = lay[slot - 1]
            ok += got == f; tot += 1
            row.append(f"{f[:4]}→칸{slot}({got[:4]}){'O' if got == f else 'X'} pan{end[0]:+.0f}")
        print(f"  {name} [{'/'.join(x[:4] for x in lay)}]  " + "  ".join(row))
    print(f"  맞음 {ok}/{tot}")
