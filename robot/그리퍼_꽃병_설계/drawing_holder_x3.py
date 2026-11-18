"""3구 꽃병 치수 도면 (PNG). make_parts.py의 설계 값을 그대로 사용."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon
import make_parts as P

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
L = (P.ROW_N - 1) * P.ROW_PITCH + P.ROW_DEPTH
W = P.ROW_DEPTH
xs = [(i - (P.ROW_N - 1) / 2) * P.ROW_PITCH for i in range(P.ROW_N)]


def dim(ax, x0, y0, x1, y1, text, off=(0, 0), rot=0):
    ax.annotate("", (x0, y0), (x1, y1), arrowprops=dict(arrowstyle="<->", lw=0.9))
    ax.text((x0 + x1) / 2 + off[0], (y0 + y1) / 2 + off[1], text, ha="center", va="center", fontsize=9,
            rotation=rot, bbox=dict(fc="white", ec="none", pad=1))


fig, (a, b) = plt.subplots(2, 1, figsize=(11, 9), gridspec_kw=dict(height_ratios=[1, 1.15]))
# 위에서 본 모습
a.add_patch(FancyBboxPatch((-L / 2 + 8, -W / 2 + 8), L - 16, W - 16, boxstyle="round,pad=8", fc="#d9efe1", ec="k"))
for i, x in enumerate(xs):
    a.add_patch(Circle((x, 0), P.HOLDER_FUNNEL_R + 2.5, fc="#a8d8b9", ec="k"))
    a.add_patch(Circle((x, 0), P.HOLDER_FUNNEL_R, fc="white", ec="k", ls="--"))
    a.add_patch(Circle((x, 0), P.HOLDER_HOLE_R, fc="#555", ec="k"))
    for k in range(i + 1):
        a.add_patch(Circle((x + (k - i / 2) * 6, -W / 2 + 7), 2, fc="k"))
    a.text(x, -W / 2 - 6, f"{i + 1}번 칸", ha="center", fontsize=10)
dim(a, -L / 2, W / 2 + 10, L / 2, W / 2 + 10, f"{L:.0f}")
dim(a, xs[0], W / 2 + 3, xs[1], W / 2 + 3, f"{P.ROW_PITCH:.0f}", off=(0, 3))
dim(a, xs[1], W / 2 + 3, xs[2], W / 2 + 3, f"{P.ROW_PITCH:.0f}", off=(0, 3))
dim(a, L / 2 + 8, -W / 2, L / 2 + 8, W / 2, f"{W:.0f}", rot=90, off=(4, 0))
a.text(-L / 2 - 12, W / 2 + 14, f"구멍 Ø{2 * P.HOLDER_HOLE_R:.0f}\n깔때기 입구 Ø{2 * P.HOLDER_FUNNEL_R:.0f}\n깔때기 바깥 Ø{2 * (P.HOLDER_FUNNEL_R + 2.5):.0f}",
       fontsize=8, va="bottom")
a.set_title("위에서 본 모습 (단위 mm, 앞쪽 = 아래쪽, 점 개수 = 칸 번호)")
a.set_xlim(-L / 2 - 15, L / 2 + 25); a.set_ylim(-W / 2 - 14, W / 2 + 30); a.set_aspect("equal"); a.axis("off")

# 앞에서 자른 단면 (가운데 칸)
H, FH, BH, TR, HR, FR, FL = P.HOLDER_H, P.HOLDER_FUNNEL_H, P.HOLDER_BASE_H, P.HOLDER_TUBE_R, P.HOLDER_HOLE_R, P.HOLDER_FUNNEL_R, P.HOLDER_FLOOR
b.add_patch(Polygon([(-L / 2, 0), (L / 2, 0), (L / 2, BH), (-L / 2, BH)], fc="#d9efe1", ec="k"))
for x in xs:
    outer = [(x - TR, 0), (x - TR, H - FH), (x - FR - 2.5, H), (x - FR, H), (x - HR, H - FH), (x - HR, FL),
             (x + HR, FL), (x + HR, H - FH), (x + FR, H), (x + FR + 2.5, H), (x + TR, H - FH), (x + TR, 0)]
    b.add_patch(Polygon(outer, fc="#a8d8b9", ec="k"))
    for s in (-1, 1):
        b.add_patch(Polygon([(x + s * TR, BH), (x + s * (W / 2 - 6) * 0.707, BH), (x + s * TR, BH + 25)], fc="#c4e6cf", ec="k", lw=0.6))
dim(b, -L / 2 - 8, 0, -L / 2 - 8, H, f"{H:.0f}", rot=90, off=(-4, 0))
dim(b, xs[0] - 34, 0, xs[0] - 34, BH, f"{BH:.0f}", rot=90, off=(-4, 0))
dim(b, xs[2] + 26, H - FH, xs[2] + 26, H, f"{FH:.0f}", rot=90, off=(4, 0))
dim(b, xs[1] - HR, H / 2, xs[1] + HR, H / 2, f"Ø{2 * HR:.0f}", off=(0, 4))
dim(b, xs[1] - TR, 30, xs[1] + TR, 30, f"Ø{2 * TR:.0f}", off=(0, -4))
b.text(xs[1] + 14, BH + 12, f"구멍 깊이 {H - FL:.0f} (바닥 {FL:.0f})", fontsize=8)
b.text(xs[0] + 14, BH + 28, "보강 리브 4개/칸 (높이 25)", fontsize=8)
b.text(0, -9, f"밑면: 칸마다 링 모양 무게추 홈 (깊이 3.5, Ø{2 * (TR + 2):.0f}~Ø{min(P.ROW_PITCH, W) - 10:.0f}) — 동전/너트 넣고 테이프", ha="center", fontsize=8)
b.set_title("앞에서 본 단면 (단위 mm)")
b.set_xlim(-L / 2 - 20, L / 2 + 25); b.set_ylim(-14, H + 8); b.set_aspect("equal"); b.axis("off")
fig.suptitle("3구 꽃병 flower_holder_x3.stl", fontsize=13)
plt.tight_layout()
plt.savefig("도면_꽃병3구.png", dpi=130)
print("saved")
