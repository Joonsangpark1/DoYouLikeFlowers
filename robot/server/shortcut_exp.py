"""배치/시작분포 지름길 검사 (11-25). 540 snoise2 모델.
E1 꽃 가리기 / 배경 가리기, E2 배경 바꿔치기, E3 배치 판별 probe, E4 시점 이동(시작 자세 변화 대용), E5 노이즈(ε) 시드별 칸 변화.
사용: python shortcut_exp.py <pretrained_model> [preview|all]
결과: ~/lerobot_flower/shortcut_1125/
"""
import json, os, sys, glob, time
from collections import defaultdict
import numpy as np, torch, cv2
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.policies.factory import make_pre_post_processors

OUT = os.path.expanduser("~/lerobot_flower/shortcut_1125"); os.makedirs(OUT, exist_ok=True)
root = os.path.expanduser("~/lerobot_data/parkjoonsang/flower_reach_trial4_540")
ds = LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log = {r["episode_index"]: r for r in map(json.loads, open(root + "_collection_log.jsonl"))}
fr, to = list(ds.meta.episodes["dataset_from_index"]), list(ds.meta.episodes["dataset_to_index"])
N = len(fr)
A = np.stack(ds.hf_dataset.with_format("numpy")["action"]); S = np.stack(ds.hf_dataset.with_format("numpy")["observation.state"])
LAY = [tuple(log[e]["layout"][k] for k in "123") for e in range(N)]
LS = ["-".join(x[0].upper() for x in l) for l in LAY]
DATE = [log[e]["time"][5:10] for e in range(N)]
mean0 = torch.from_numpy(S[fr].mean(0).astype(np.float32))
slot_c = {s: np.mean([A[to[e] - 1][:4] for e in range(N) if log[e]["target_slot"] == s], 0) for s in (1, 2, 3)}
FL = ["rose", "blue", "sunflower"]
TASK = {"rose": "Move the gripper close to the pink rose.", "blue": "Move the gripper close to the blue flower.",
        "sunflower": "Move the gripper close to the yellow sunflower."}
REAL_LAYOUT = {k: ("rose", "blue", "sunflower") for k in ["1121_230141", "1121_230242", "1121_230337", "1121_230508", "1121_230610", "1121_230658", "1121_230745"]}
REAL_LAYOUT["1121_230848"] = ("sunflower", "blue", "rose"); REAL_LAYOUT["1121_230956"] = ("blue", "sunflower", "rose")
REAL_LAYOUT["1122_150640"] = REAL_LAYOUT["1122_161618"] = REAL_LAYOUT["1122_161741"] = ("blue", "sunflower", "rose")
REAL_LAYOUT["1122_162022"] = REAL_LAYOUT["1122_162113"] = ("sunflower", "rose", "blue")

ck = sys.argv[1]; MODE = sys.argv[2] if len(sys.argv) > 2 else "all"
GRAY = 128


def u8(e):
    return (ds[fr[e]]["observation.images.front"].permute(1, 2, 0).numpy() * 255).astype(np.uint8)


def ten(u):
    return torch.from_numpy(np.ascontiguousarray(u)).permute(2, 0, 1).float() / 255


def fmask(u):
    h = cv2.cvtColor(u, cv2.COLOR_RGB2HSV); H, Sa, V = [h[..., i].astype(int) for i in range(3)]
    m = (((H >= 160) | (H <= 8)) & (Sa >= 60) & (V >= 120)) | ((H >= 95) & (H <= 125) & (Sa >= 60) & (V >= 90)) | ((H >= 15) & (H <= 35) & (Sa >= 110) & (V >= 140))
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = np.zeros_like(m)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] >= 0.003 * m.size:
            keep[lab == i] = 1
    return cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))).astype(bool)


def noflower(u, m):
    x = u.copy(); x[m] = GRAY; return x


def nobg(u, m):
    x = u.copy(); x[~m] = GRAY; return x


def swap(uA, mA, uB, mB):
    x = uB.copy(); x[mB] = GRAY; x[mA] = uA[mA]; return x


def shift(u, dx=0.0, dy=0.0, rot=0.0):
    h, w = u.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), rot, 1.0); M[0, 2] += dx * w; M[1, 2] += dy * h
    return cv2.warpAffine(u, M, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))


rng = np.random.default_rng(0)
partner = {e: int(rng.choice([b for b in range(N) if LAY[b] != LAY[e]])) for e in range(N)}

if MODE == "preview":
    tiles = []
    for e in [0, 100, 200, 300, 400, 500]:
        u = u8(e); m = fmask(u); b = partner[e]; ub = u8(b); mb = fmask(ub)
        row = [u, noflower(u, m), nobg(u, m), swap(u, m, ub, mb), shift(u, 0.10), shift(u, 0, 0, 10)]
        row = [cv2.putText(cv2.resize(x.copy(), (256, 192)), t, (5, 20), 0, 0.6, (255, 0, 0), 2) for x, t in zip(row, [f"ep{e} {LS[e]}", "noflower", "nobg", f"swap bg={LS[b]}", "dx+10%", "rot+10"])]
        tiles.append(np.hstack(row)); print(e, LS[e], "mask cover %.1f%%" % (m.mean() * 100))
    cv2.imwrite(f"{OUT}/preview.jpg", cv2.cvtColor(np.vstack(tiles), cv2.COLOR_RGB2BGR))
    sys.exit()

policy = SmolVLAPolicy.from_pretrained(ck).to("cuda").eval()
pre, post = make_pre_post_processors(policy.config, pretrained_path=ck)
cap = {}
_vf = policy.model.vlm_with_expert.forward


def _wrapped(*a, **k):
    o = _vf(*a, **k)
    if cap.get("want") and "h" not in cap and o[0][0] is not None:
        cap["h"] = o[0][0].float().mean(1)[0].cpu().numpy()
    return o


policy.model.vlm_with_expert.forward = _wrapped


@torch.no_grad()
def predict(u, f, seed=0, want=False):
    torch.manual_seed(seed); cap.clear(); cap["want"] = want
    ch = post(policy.predict_action_chunk(pre({"observation.images.camera1": ten(u), "observation.state": mean0, "task": TASK[f]})))[0].float().cpu().numpy()
    s = min(slot_c, key=lambda k: np.linalg.norm(ch[-1][:4] - slot_c[k]))
    return s, float(ch[-1][0]), cap.get("h")


t0 = time.time()
out = open(f"{OUT}/result.txt", "w")


def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.write(s + "\n"); out.flush()


P(f"model {ck}\nslot centers pan " + " ".join(f"{k}:{v[0]:+.1f}" for k, v in slot_c.items()))

# ---------- E1/E2: 학습 첫 사진 (2개마다) ----------
acc = defaultdict(lambda: [0, 0]); acc_l = defaultdict(lambda: [0, 0]); agree = [0, 0]
sw = defaultdict(int); sw_l = defaultdict(lambda: defaultdict(int)); cover = []
for e in range(0, N, 2):
    u = u8(e); m = fmask(u); cover.append(m.mean()); b = partner[e]; ub = u8(b); mb = fmask(ub)
    imgs = {"orig": u, "noflower": noflower(u, m), "nobg": nobg(u, m)}
    for f in FL:
        s0 = None
        for c, x in imgs.items():
            s, _, _ = predict(x, f)
            ok = LAY[e][s - 1] == f
            acc[c][0] += ok; acc[c][1] += 1; acc_l[(c, LS[e])][0] += ok; acc_l[(c, LS[e])][1] += 1
            if c == "orig": s0 = s
            if c == "noflower": agree[0] += s == s0; agree[1] += 1
        if LAY[e].index(f) != LAY[b].index(f):
            s, _, _ = predict(swap(u, m, ub, mb), f)
            k = "꽃(A)따름" if LAY[e][s - 1] == f else "배경(B)따름" if LAY[b][s - 1] == f else "둘다아님"
            sw[k] += 1; sw_l[LS[e]][k] += 1
P(f"\n[E1] 학습 첫 사진 {len(cover)}장 x 지시문 3 (꽃 마스크 면적 평균 {np.mean(cover)*100:.1f}%, 우연=33%)")
for c in ["orig", "noflower", "nobg"]:
    P(f"  {c:9s} 정답칸 {acc[c][0]}/{acc[c][1]} = {acc[c][0]/acc[c][1]:.0%}")
P(f"  noflower 예측이 원본과 같은 칸: {agree[0]}/{agree[1]} = {agree[0]/agree[1]:.0%}")
P("  배치별 정답률 (orig / noflower / nobg):")
for L in sorted(set(LS)):
    P("   " + L + "  " + "  ".join(f"{acc_l[(c,L)][0]}/{acc_l[(c,L)][1]}" for c in ["orig", "noflower", "nobg"]))
ns = sum(sw.values())
P(f"\n[E2] 배경 바꿔치기 (A의 꽃 + 다른 배치 B의 배경, A·B가 다른 칸을 가리키는 경우만) n={ns}")
P("  " + "  ".join(f"{k} {v} ({v/ns:.0%})" for k, v in sw.items()))
for L in sorted(sw_l):
    n = sum(sw_l[L].values()); P(f"   꽃배치 {L}: " + "  ".join(f"{k} {v}" for k, v in sw_l[L].items()) + f" / {n}")
P(f"  ({time.time()-t0:.0f}s)")

# ---------- 실물 첫 사진 ----------
racc = defaultdict(lambda: [0, 0]); rows = []
for p in sorted(glob.glob(os.path.expanduser("~/lerobot_flower/realframes_1121/*.jpg"))):
    name = os.path.basename(p)[:11]; L = REAL_LAYOUT[name]
    u = cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2RGB); m = fmask(u)
    r = []
    for c, x in {"orig": u, "noflower": noflower(u, m), "nobg": nobg(u, m)}.items():
        k = 0
        for f in FL:
            s, _, _ = predict(x, f); ok = L[s - 1] == f; k += ok; racc[c][0] += ok; racc[c][1] += 1
        r.append(f"{c} {k}/3")
    rows.append(f"   {name} [{'-'.join(x[0].upper() for x in L)}] " + "  ".join(r))
P(f"\n[E1-실물] 실물 첫 사진 14장 x 지시문 3")
for c in ["orig", "noflower", "nobg"]:
    P(f"  {c:9s} {racc[c][0]}/{racc[c][1]} = {racc[c][0]/racc[c][1]:.0%}")
for r in rows: P(r)

# ---------- E3: probe ----------
feats = defaultdict(list); pix = defaultdict(list)
for e in range(N):
    u = u8(e); m = fmask(u)
    for c, x in {"orig": u, "noflower": noflower(u, m), "nobg": nobg(u, m)}.items():
        _, _, h = predict(x, "rose", want=True); feats[c].append(h)
        pix[c].append(cv2.resize(x, (32, 24), interpolation=cv2.INTER_AREA).reshape(-1) / 255.0)


def probe(X, y, folds=5, l2=1e-2, it=300):
    X = np.asarray(X, np.float32); classes = sorted(set(y)); Y = np.array([classes.index(v) for v in y])
    idx = np.random.default_rng(0).permutation(len(Y)); parts = np.array_split(idx, folds); correct = 0
    for k in range(folds):
        te = parts[k]; tr = np.concatenate([parts[j] for j in range(folds) if j != k])
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
        Xt = torch.tensor((X[tr] - mu) / sd); Xe = torch.tensor((X[te] - mu) / sd)
        W = torch.zeros(X.shape[1], len(classes), requires_grad=True); bb = torch.zeros(len(classes), requires_grad=True)
        opt = torch.optim.LBFGS([W, bb], max_iter=it, line_search_fn="strong_wolfe"); yt = torch.tensor(Y[tr])

        def closure():
            opt.zero_grad(); l = torch.nn.functional.cross_entropy(Xt @ W + bb, yt) + l2 * (W ** 2).sum(); l.backward(); return l
        opt.step(closure)
        correct += ((Xe @ W + bb).argmax(1).numpy() == Y[te]).sum()
    return correct / len(Y), 1 / len(classes)


P(f"\n[E3] 배치 판별 선형 probe (5-fold, 540장, 지시문 rose 고정, 상태 평균 고정)")
for tgt, lab in [("배치(6)", LS), ("수집날짜", DATE)]:
    for c in ["orig", "noflower", "nobg"]:
        a1, ch = probe(feats[c], lab); a2, _ = probe(pix[c], lab)
        P(f"  {tgt:7s} {c:9s} VLM특징 {a1:.0%}  픽셀32x24 {a2:.0%}  (우연 {ch:.0%})")
P(f"  ({time.time()-t0:.0f}s)")

# ---------- E4: 시점 이동 ----------
TF = {"orig": {}, "dx-15%": dict(dx=-.15), "dx-10%": dict(dx=-.10), "dx-5%": dict(dx=-.05), "dx+5%": dict(dx=.05), "dx+10%": dict(dx=.10), "dx+15%": dict(dx=.15),
      "dy-10%": dict(dy=-.10), "dy+10%": dict(dy=.10), "rot-10": dict(rot=-10), "rot-5": dict(rot=-5), "rot+5": dict(rot=5), "rot+10": dict(rot=10)}
e4 = defaultdict(lambda: [0, 0]); pans = defaultdict(list)
for e in range(0, N, 6):
    u = u8(e)
    for t, kw in TF.items():
        x = shift(u, **kw) if kw else u
        for f in FL:
            s, pan, _ = predict(x, f); e4[t][0] += LAY[e][s - 1] == f; e4[t][1] += 1; pans[(t, f)].append(pan)
P(f"\n[E4] 시점 이동 (학습 첫 사진 6개마다 x 지시문 3; 학습 증강은 회전±5°/이동5%까지였음)")
for t in TF:
    P(f"  {t:7s} 정답칸 {e4[t][0]}/{e4[t][1]} = {e4[t][0]/e4[t][1]:.0%}")

# ---------- E5: 노이즈 시드 ----------
def seeds_eval(items, K=8):
    changed = 0; tot = 0; maj = 0; per = 0; sd = []
    for u, L in items:
        for f in FL:
            r = [predict(u, f, seed=k) for k in range(K)]
            sl = [x[0] for x in r]; sd.append(np.std([x[1] for x in r]))
            changed += len(set(sl)) > 1; tot += 1
            per += sum(L[s - 1] == f for s in sl) / K
            mj = max(set(sl), key=sl.count); maj += L[mj - 1] == f
    return changed, tot, per / tot, maj / tot, float(np.mean(sd))


tr_items = [(u8(e), LAY[e]) for e in range(0, N, 9)]
re_items = [(cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2RGB), REAL_LAYOUT[os.path.basename(p)[:11]]) for p in sorted(glob.glob(os.path.expanduser("~/lerobot_flower/realframes_1121/*.jpg")))]
P(f"\n[E5] 초기 노이즈 시드 8개 (같은 사진·지시문·상태)")
for nm, it in [("학습사진", tr_items), ("실물사진", re_items)]:
    c, t, per, mj, sd = seeds_eval(it)
    P(f"  {nm}: 시드에 따라 칸이 바뀌는 경우 {c}/{t} = {c/t:.0%}, 시드 평균 정답률 {per:.0%}, 다수결 정답률 {mj:.0%}, 끝 pan 표준편차 평균 {sd:.1f}°")
P(f"\n총 {time.time()-t0:.0f}s")
