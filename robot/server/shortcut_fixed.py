"""E1b/E2b: 꽃 실루엣 모양이 새지 않게, 모든 사진에 같은 고정 마스크 사용 (11-25).
고정 마스크 = 학습 첫 사진 540장 중 THR 이상에서 꽃 색으로 잡힌 픽셀 (사진마다 같음).
사용: python shortcut_fixed.py <pretrained_model> [THR]
"""
import sys, os, importlib.util
import numpy as np, torch, cv2
from collections import defaultdict
sys.argv = [sys.argv[0], sys.argv[1], "lib"] + sys.argv[2:]
THR = float(sys.argv[3]) if len(sys.argv) > 3 else 0.15
spec = importlib.util.spec_from_file_location("se", os.path.expanduser("~/lerobot_flower/shortcut_exp.py"))
src = open(spec.origin).read().split("t0 = time.time()")[0]  # 모델 로딩·함수까지만
g = {"__name__": "se"}; exec(compile(src, spec.origin, "exec"), g)
N, u8, fmask, predict, LAY, LS, FL, partner, OUT, GRAY = [g[k] for k in "N u8 fmask predict LAY LS FL partner OUT GRAY".split()]

freq = np.mean([fmask(u8(e)) for e in range(N)], 0)
FM = freq >= THR
out = open(f"{OUT}/result_fixed_{THR}.txt", "w")


def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.write(s + "\n"); out.flush()


P(f"고정 마스크 THR={THR}: 화면의 {FM.mean()*100:.1f}% (꽃이 그 자리에 나온 사진 비율 >= {THR})")
vis = (np.stack([freq] * 3, -1) * 255).astype(np.uint8); vis[FM] = (vis[FM] * 0.5 + np.array([255, 0, 0]) * 0.5).astype(np.uint8)
ex = u8(0).copy(); ex[FM] = GRAY; ex2 = u8(0).copy(); ex2[~FM] = GRAY
cv2.imwrite(f"{OUT}/fixedmask_{THR}.jpg", cv2.cvtColor(np.hstack([vis, ex, ex2]), cv2.COLOR_RGB2BGR))

acc = defaultdict(lambda: [0, 0]); accl = defaultdict(lambda: [0, 0]); sw = defaultdict(int)
for e in range(0, N, 2):
    u = u8(e); b = partner[e]; ub = u8(b)
    out_zone = u.copy(); out_zone[FM] = GRAY  # 꽃 자리 전부 회색 (바깥만 보임)
    in_zone = u.copy(); in_zone[~FM] = GRAY   # 꽃 자리만 보임
    sw_img = ub.copy(); sw_img[FM] = u[FM]     # 꽃 자리 = A, 바깥 = B
    for f in FL:
        for c, x in {"바깥만": out_zone, "꽃자리만": in_zone}.items():
            s, _, _ = predict(x, f); ok = LAY[e][s - 1] == f
            acc[c][0] += ok; acc[c][1] += 1; accl[(c, LS[e])][0] += ok; accl[(c, LS[e])][1] += 1
        if LAY[e].index(f) != LAY[b].index(f):
            s, _, _ = predict(sw_img, f)
            sw["꽃자리(A)따름" if LAY[e][s - 1] == f else "바깥(B)따름" if LAY[b][s - 1] == f else "둘다아님"] += 1
P(f"\n[E1b] 학습 첫 사진 {len(range(0, N, 2))}장 x 지시문 3 (우연 33%)")
for c in acc:
    P(f"  {c:6s} 정답칸 {acc[c][0]}/{acc[c][1]} = {acc[c][0]/acc[c][1]:.0%}")
for L in sorted(set(LS)):
    P("   " + L + "  " + "  ".join(f"{c} {accl[(c,L)][0]}/{accl[(c,L)][1]}" for c in acc))
ns = sum(sw.values())
P(f"\n[E2b] 꽃자리=A, 바깥=B (A·B가 다른 칸) n={ns}: " + "  ".join(f"{k} {v} ({v/ns:.0%})" for k, v in sw.items()))
