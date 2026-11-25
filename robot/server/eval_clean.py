"""11-25 이상치 제거 비교 평가. 모든 모델을 같은 사진·같은 시드로.
①실물 첫 사진 14장 x 지시문 3 x 시드 8 ②학습 첫 사진(원본 540, 3개마다) x 지시문 3, 배치별 ③고정 마스크 꽃자리만/바깥만
사용: python eval_clean.py 이름=<pretrained_model> ...   결과 ~/lerobot_flower/clean_eval_1125.txt
"""
import json, os, sys, glob
from collections import defaultdict
import numpy as np, torch, cv2
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.policies.factory import make_pre_post_processors

root = os.path.expanduser("~/lerobot_data/parkjoonsang/flower_reach_trial4_540")
ds = LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log = {r["episode_index"]: r for r in map(json.loads, open(root + "_collection_log.jsonl"))}
fr, to = list(ds.meta.episodes["dataset_from_index"]), list(ds.meta.episodes["dataset_to_index"]); N = len(fr)
A = np.stack(ds.hf_dataset.with_format("numpy")["action"]); S = np.stack(ds.hf_dataset.with_format("numpy")["observation.state"])
LAY = [tuple(log[e]["layout"][k] for k in "123") for e in range(N)]; LS = ["-".join(x[0].upper() for x in l) for l in LAY]
mean0 = torch.from_numpy(S[fr].mean(0).astype(np.float32))
slot_c = {s: np.mean([A[to[e] - 1][:4] for e in range(N) if log[e]["target_slot"] == s], 0) for s in (1, 2, 3)}
FL = ["rose", "blue", "sunflower"]
TASK = {"rose": "Move the gripper close to the pink rose.", "blue": "Move the gripper close to the blue flower.", "sunflower": "Move the gripper close to the yellow sunflower."}
RL = {k: ("rose", "blue", "sunflower") for k in ["1121_230141", "1121_230242", "1121_230337", "1121_230508", "1121_230610", "1121_230658", "1121_230745"]}
RL["1121_230848"] = ("sunflower", "blue", "rose"); RL["1121_230956"] = ("blue", "sunflower", "rose")
RL["1122_150640"] = RL["1122_161618"] = RL["1122_161741"] = ("blue", "sunflower", "rose"); RL["1122_162022"] = RL["1122_162113"] = ("sunflower", "rose", "blue")
REAL = [(os.path.basename(p)[:11], cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2RGB)) for p in sorted(glob.glob(os.path.expanduser("~/lerobot_flower/realframes_1121/*.jpg")))]
TR = [(e, (ds[fr[e]]["observation.images.front"].permute(1, 2, 0).numpy() * 255).astype(np.uint8)) for e in range(0, N, 3)]


def fmask(u):
    h = cv2.cvtColor(u, cv2.COLOR_RGB2HSV); H, Sa, V = [h[..., i].astype(int) for i in range(3)]
    m = (((H >= 160) | (H <= 8)) & (Sa >= 60) & (V >= 120)) | ((H >= 95) & (H <= 125) & (Sa >= 60) & (V >= 90)) | ((H >= 15) & (H <= 35) & (Sa >= 110) & (V >= 140))
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m); keep = np.zeros_like(m)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] >= 0.003 * m.size: keep[lab == i] = 1
    return cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))).astype(bool)


FM = np.mean([fmask(u8) for _, u8 in TR], 0) >= 0.15
out = open(os.path.expanduser("~/lerobot_flower/clean_eval_1125.txt"), "a")


def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.write(s + "\n"); out.flush()


for arg in sys.argv[1:]:
    name, ck = arg.split("=", 1)
    pol = SmolVLAPolicy.from_pretrained(ck).to("cuda").eval(); pre, post = make_pre_post_processors(pol.config, pretrained_path=ck)

    @torch.no_grad()
    def slot(u, f, seed=0):
        torch.manual_seed(seed)
        ch = post(pol.predict_action_chunk(pre({"observation.images.camera1": torch.from_numpy(np.ascontiguousarray(u)).permute(2, 0, 1).float() / 255, "observation.state": mean0, "task": TASK[f]})))[0].float().cpu().numpy()
        return min(slot_c, key=lambda k: np.linalg.norm(ch[-1][:4] - slot_c[k]))

    real = [0, 0]; real_new = [0, 0]; real_s0 = [0, 0]
    for nm, u in REAL:
        for f in FL:
            for sd in range(8):
                ok = RL[nm][slot(u, f, sd) - 1] == f; real[0] += ok; real[1] += 1
                if sd == 0: real_s0[0] += ok; real_s0[1] += 1
                if RL[nm] != ("rose", "blue", "sunflower"): real_new[0] += ok; real_new[1] += 1
    tb = defaultdict(lambda: [0, 0]); fz = [0, 0]; oz = [0, 0]
    for e, u in TR:
        uin = u.copy(); uin[~FM] = 128; uout = u.copy(); uout[FM] = 128
        for f in FL:
            ok = LAY[e][slot(u, f) - 1] == f; tb[LS[e]][0] += ok; tb[LS[e]][1] += 1
            fz[0] += LAY[e][slot(uin, f) - 1] == f; fz[1] += 1; oz[0] += LAY[e][slot(uout, f) - 1] == f; oz[1] += 1
    tt = [sum(v[0] for v in tb.values()), sum(v[1] for v in tb.values())]
    P(f"{name:6s} 실물(시드8) {real[0]/real[1]:.1%} [{real[0]}/{real[1]}]  실물 시드0 {real_s0[0]}/{real_s0[1]}  실물 배치5장면 제외 {real_new[0]/real_new[1]:.1%}  "
      f"| 학습사진 {tt[0]/tt[1]:.1%}  꽃자리만 {fz[0]/fz[1]:.1%}  바깥만 {oz[0]/oz[1]:.1%}  | 배치별 " + " ".join(f"{L} {v[0]}/{v[1]}" for L, v in sorted(tb.items())))
    del pol; torch.cuda.empty_cache()
