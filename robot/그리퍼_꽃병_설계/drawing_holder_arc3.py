"""호 3구 꽃병 치수 도면 (PNG). make_parts.py의 설계 값을 그대로 사용."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon as MPoly
from shapely.geometry import Polygon
import make_parts as P

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
R, PITCH, W = P.ARC_R, P.ARC_PITCH, P.ROW_DEPTH
step = 2 * np.arcsin(PITCH / 2 / R)
angs = [(i - 1) * step for i in range(3)]
pos = [(R * np.sin(a), R * np.cos(a) - R) for a in angs]
a_end = abs(angs[0]) + (W / 2 - 4) / R
ts = np.linspace(-a_end, a_end, 120)
outer = [((R + W / 2) * np.sin(t), (R + W / 2) * np.cos(t) - R) for t in ts]
inner = [((R - W / 2) * np.sin(t), (R - W / 2) * np.cos(t) - R) for t in ts[::-1]]
plate = Polygon(outer + inner).buffer(-8).buffer(8)
bx0, by0, bx1, by1 = plate.bounds


def dim(ax, p0, p1, text, off=(0, 0), rot=0):
    ax.annotate("", p0, p1, arrowprops=dict(arrowstyle="<->", lw=0.9))
    ax.text((p0[0] + p1[0]) / 2 + off[0], (p0[1] + p1[1]) / 2 + off[1], text, ha="center", va="center",
            fontsize=9, rotation=rot, bbox=dict(fc="white", ec="none", pad=1))


fig, ax = plt.subplots(figsize=(11, 8.5))
ax.add_patch(MPoly(np.array(plate.exterior.coords), fc="#d9efe1", ec="k"))
for i, ((x, y), a) in enumerate(zip(pos, angs)):
    ax.add_patch(Circle((x, y), P.HOLDER_FUNNEL_R + 2.5, fc="#a8d8b9", ec="k"))
    ax.add_patch(Circle((x, y), P.HOLDER_FUNNEL_R, fc="white", ec="k", ls="--"))
    ax.add_patch(Circle((x, y), P.HOLDER_HOLE_R, fc="#555", ec="k"))
    rr = R - W / 2 + 7
    for k in range(i + 1):
        t = a + (k - i / 2) * 6 / rr
        ax.add_patch(Circle((rr * np.sin(t), rr * np.cos(t) - R), 2, fc="k"))
    ax.text(x, y + 30, f"{i + 1}번 칸", ha="center", fontsize=10)
    ax.plot([0, x], [-R, y], color="tab:blue", lw=0.7, ls=":")
# 호 중심선
tt = np.linspace(-a_end, a_end, 80)
ax.plot(R * np.sin(tt), R * np.cos(tt) - R, color="tab:blue", lw=0.7, ls="--")
ax.plot(0, -R, "o", color="tab:blue")
ax.text(0, -R - 12, f"호 중심 (로봇 베이스를 여기에)\n각 구멍까지 {R:.0f}", ha="center", va="top", fontsize=9, color="tab:blue")
dim(ax, pos[0], pos[1], f"{PITCH:.0f}", off=(0, 8))
dim(ax, pos[1], pos[2], f"{PITCH:.0f}", off=(0, 8))
ax.text(pos[1][0] + 35, -R / 2, f"구멍 사이 각도 {np.degrees(step):.1f}°", fontsize=9, color="tab:blue")
dim(ax, (bx0, by1 + 14), (bx1, by1 + 14), f"전체 {bx1 - bx0:.0f}")
dim(ax, (bx1 + 10, by0), (bx1 + 10, by1), f"{by1 - by0:.0f}", rot=90, off=(5, 0))
ax.text(bx0, by1 + 30, f"바닥 폭 {W:.0f}, 높이 {P.HOLDER_H:.0f}, 구멍 Ø{2 * P.HOLDER_HOLE_R:.0f} (깊이 {P.HOLDER_H - P.HOLDER_FLOOR:.0f}), "
        f"깔때기 입구 Ø{2 * P.HOLDER_FUNNEL_R:.0f} / 바깥 Ø{2 * (P.HOLDER_FUNNEL_R + 2.5):.0f}\n"
        f"구멍 가장자리 사이 {PITCH - 2 * P.HOLDER_HOLE_R:.0f}, 깔때기 바깥 사이 {PITCH - 2 * (P.HOLDER_FUNNEL_R + 2.5):.0f}, "
        f"단면 모양은 1구/일자 3구와 같음", fontsize=9, va="bottom")
ax.set_title("호 3구 꽃병 flower_holder_arc3.stl — 위에서 본 모습 (단위 mm, 아래쪽 = 로봇 쪽, 점 개수 = 칸 번호)", fontsize=11)
ax.set_xlim(bx0 - 15, bx1 + 25); ax.set_ylim(-R - 40, by1 + 50); ax.set_aspect("equal"); ax.axis("off")
plt.tight_layout(); plt.savefig("도면_꽃병호3구.png", dpi=130); print("saved")
