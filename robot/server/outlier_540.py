"""trial4_540 에피소드 이상치 탐지 (11-25). 학습 없이 데이터만 본다.
검사: ①끝 자세 칸 vs 기록 target_slot ②첫 화면 꽃 색 위치 순서 vs 기록 배치 ③목표 꽃 가시 면적
     ④시작 상태(관절별 robust z) ⑤길이 ⑥같은 (배치,꽃) 안 궤적 이탈 ⑦끝 자세 이탈 ⑧화질(선명도·밝기)
     ⑨스텝 점프 ⑩첫 화면이 자기 배치보다 다른 배치 사진에 더 가까움(32x24 픽셀 kNN)
출력: ~/lerobot_flower/outlier_1125/{episodes.csv, summary.txt, flagged_*.jpg}
"""
import json, os, csv
from collections import defaultdict, Counter
import numpy as np, cv2
from lerobot.datasets.lerobot_dataset import LeRobotDataset

OUT = os.path.expanduser("~/lerobot_flower/outlier_1125"); os.makedirs(OUT, exist_ok=True)
root = os.path.expanduser("~/lerobot_data/parkjoonsang/flower_reach_trial4_540")
ds = LeRobotDataset("parkjoonsang/flower_reach_trial4", root=root)
log = {r["episode_index"]: r for r in map(json.loads, open(root + "_collection_log.jsonl"))}
fr, to = list(ds.meta.episodes["dataset_from_index"]), list(ds.meta.episodes["dataset_to_index"])
N = len(fr)
A = np.stack(ds.hf_dataset.with_format("numpy")["action"]); S = np.stack(ds.hf_dataset.with_format("numpy")["observation.state"])
J = ["pan", "lift", "elbow", "wflex", "roll", "grip"]
FL = ["rose", "blue", "sunflower"]
LAY = [tuple(log[e]["layout"][k] for k in "123") for e in range(N)]
LS = ["-".join(x[0].upper() for x in l) for l in LAY]
FLW = [FL[log[e]["task_index"]] for e in range(N)]
TS = [log[e]["target_slot"] for e in range(N)]


def rz(x):
    x = np.asarray(x, float); med = np.median(x); mad = np.median(np.abs(x - med)) * 1.4826 + 1e-9
    return (x - med) / mad


def hsv_masks(u):
    h = cv2.cvtColor(u, cv2.COLOR_RGB2HSV); H, Sa, V = [h[..., i].astype(int) for i in range(3)]
    return {"rose": ((H >= 160) | (H <= 8)) & (Sa >= 60) & (V >= 120), "blue": (H >= 95) & (H <= 125) & (Sa >= 60) & (V >= 90),
            "sunflower": (H >= 15) & (H <= 35) & (Sa >= 110) & (V >= 140)}


def img(i):
    return (ds[i]["observation.images.front"].permute(1, 2, 0).numpy() * 255).astype(np.uint8)


def sharp(u):
    return cv2.Laplacian(cv2.cvtColor(u, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()


slot_c = {s: np.median([A[to[e] - 1][:4] for e in range(N) if TS[e] == s], 0) for s in (1, 2, 3)}
rows = []; first_imgs = []; small = []
for e in range(N):
    a, b = fr[e], to[e]; T = b - a
    end = A[b - 1][:4]; end_slot = min(slot_c, key=lambda s: np.linalg.norm(end - slot_c[s]))
    u0 = img(a); um = img(a + T // 2); ul = img(b - 1); first_imgs.append(u0)
    small.append(cv2.resize(u0, (32, 24), interpolation=cv2.INTER_AREA).reshape(-1).astype(np.float32) / 255)
    ms = hsv_masks(u0); area = {f: ms[f].mean() for f in FL}
    cx = {f: (np.nonzero(ms[f])[1].mean() if ms[f].sum() > 0.005 * ms[f].size else None) for f in FL}
    seen = [f for f in FL if cx[f] is not None]
    order = sorted(seen, key=lambda f: cx[f])
    exp = [f for f in LAY[e] if f in seen]
    steps = np.abs(np.diff(A[a:b, :5], axis=0)).max() if T > 1 else 0
    rows.append(dict(ep=e, layout=LS[e], flower=FLW[e], target_slot=TS[e], date=log[e]["time"][:16], frames=T,
                     end_slot=end_slot, end_pan=round(float(end[0]), 1),
                     color_order="-".join(f[0].upper() for f in order), color_order_ok=int(order == exp) if len(seen) >= 2 else -1,
                     target_area=round(area[FLW[e]] * 100, 2),
                     **{f"s0_{j}": round(float(S[a][i]), 2) for i, j in enumerate(J)},
                     sharp_first=round(sharp(u0), 1), sharp_mid=round(sharp(um), 1), sharp_last=round(sharp(ul), 1),
                     bright=round(float(u0.mean()), 1), max_step=round(float(steps), 2)))
    if e % 60 == 0: print("ep", e, flush=True)

# 그룹 (배치, 꽃) 안 궤적·끝 자세 이탈
grp = defaultdict(list)
for e in range(N): grp[(LS[e], FLW[e])].append(e)
L = 60
for g, es in grp.items():
    tr = np.stack([np.stack([np.interp(np.linspace(0, to[e] - fr[e] - 1, L), np.arange(to[e] - fr[e]), A[fr[e]:to[e], j]) for j in range(4)], 1) for e in es])
    med = np.median(tr, 0); endm = np.median([A[to[e] - 1][:4] for e in es], 0)
    for k, e in enumerate(es):
        rows[e]["traj_dev"] = round(float(np.abs(tr[k] - med).mean()), 2)
        rows[e]["end_dev"] = round(float(np.linalg.norm(A[to[e] - 1][:4] - endm)), 2)
# 첫 화면 kNN: 가장 가까운 5장 중 자기 배치가 몇 장인지
X = np.stack(small); X = (X - X.mean(0)) / (X.std(0) + 1e-6)
D = ((X[:, None] - X[None]) ** 2).sum(-1); np.fill_diagonal(D, np.inf)
for e in range(N):
    nn = np.argsort(D[e])[:5]; rows[e]["knn_same_batch"] = int(sum(LS[n] == LS[e] for n in nn)); rows[e]["knn_dist"] = round(float(np.sqrt(D[e, nn[0]])), 1)

# robust z
cols_z = ["frames", "traj_dev", "end_dev", "max_step", "bright"] + [f"s0_{j}" for j in J]
for c in cols_z:
    z = rz([r[c] for r in rows])
    for r, v in zip(rows, z): r["z_" + c] = round(float(v), 1)
zs = rz(np.log([r["sharp_first"] + 1 for r in rows]))
for r, v in zip(rows, zs): r["z_sharp_first"] = round(float(v), 1)

FLAGS = {
    "끝칸≠기록칸": lambda r: r["end_slot"] != r["target_slot"],
    "색순서≠기록배치": lambda r: r["color_order_ok"] == 0,
    "목표꽃 거의안보임(<1%)": lambda r: r["target_area"] < 1.0,
    "시작상태 이탈(|z|>4)": lambda r: any(abs(r[f"z_s0_{j}"]) > 4 for j in J[:5]),
    "길이 이탈(|z|>4)": lambda r: abs(r["z_frames"]) > 4,
    "궤적 이탈(z>4)": lambda r: r["z_traj_dev"] > 4,
    "끝자세 이탈(z>4)": lambda r: r["z_end_dev"] > 4,
    "흐림(z<-3)": lambda r: r["z_sharp_first"] < -3,
    "밝기 이탈(|z|>4)": lambda r: abs(r["z_bright"]) > 4,
    "스텝 점프(z>6)": lambda r: r["z_max_step"] > 6,
    "kNN 이웃이 다른배치(<=1/5)": lambda r: r["knn_same_batch"] <= 1,
}
for r in rows: r["flags"] = ";".join(k for k, f in FLAGS.items() if f(r))
with open(f"{OUT}/episodes.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

out = open(f"{OUT}/summary.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.write(s + "\n")
P(f"trial4_540 이상치 검사: {N} 에피소드")
P("칸 중심 pan(끝 action 중앙값): " + " ".join(f"{s}:{v[0]:+.1f}" for s, v in slot_c.items()))
P("관절별 시작상태 중앙값/MAD: " + "  ".join(f"{j} {np.median(S[fr][:, i]):+.1f}/{np.median(np.abs(S[fr][:, i]-np.median(S[fr][:, i])))*1.4826:.2f}" for i, j in enumerate(J)))
P("")
for k, f in FLAGS.items():
    es = [r["ep"] for r in rows if f(r)]
    by = Counter(rows[e]["layout"] for e in es)
    P(f"{k:22s} {len(es):3d}개  배치별 {dict(by)}  예: {es[:15]}")
nflag = [r for r in rows if r["flags"]]
P(f"\n플래그 1개 이상: {len(nflag)}개, 2개 이상: {sum(1 for r in rows if r['flags'].count(';') >= 1)}개")
P("\n배치·꽃별 목표꽃 가시면적 중앙값(%) / 끝칸 일치율:")
for g in sorted(grp):
    es = grp[g]
    P(f"  {g[0]} {g[1]:9s} n={len(es):3d}  면적 {np.median([rows[e]['target_area'] for e in es]):5.1f}  끝칸일치 {np.mean([rows[e]['end_slot']==rows[e]['target_slot'] for e in es]):.0%}  궤적이탈 중앙 {np.median([rows[e]['traj_dev'] for e in es]):.1f}°")
P("\n세션(날짜)별: " + "  ".join(f"{d} {c}" for d, c in sorted(Counter(r['date'][:10] for r in rows).items())))
P("\n플래그 2개 이상 에피소드:")
for r in rows:
    if r["flags"].count(";") >= 1:
        P(f"  ep{r['ep']:3d} {r['layout']} {r['flower']:9s} {r['date']}  {r['flags']}")

# 그림: 플래그 종류별 최대 8장
for k, f in FLAGS.items():
    es = [r["ep"] for r in rows if f(r)][:8]
    if not es: continue
    tiles = []
    for e in es:
        t = cv2.resize(first_imgs[e], (320, 240)).copy()
        cv2.putText(t, f"ep{e} {LS[e]} {FLW[e][:4]} s{TS[e]}->{rows[e]['end_slot']}", (5, 22), 0, 0.6, (255, 0, 0), 2)
        tiles.append(t)
    while len(tiles) % 4: tiles.append(np.zeros_like(tiles[0]))
    g = np.vstack([np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)])
    safe = "".join(ch if ch.isalnum() else "_" for ch in k)
    cv2.imwrite(f"{OUT}/flagged_{safe}.jpg", cv2.cvtColor(g, cv2.COLOR_RGB2BGR))
print("done")
