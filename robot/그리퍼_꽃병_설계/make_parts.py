"""
SO-101 그리퍼용 교체형 넓은 패드 + 꽃병(꽃 세우개) STL 생성기.

원래 그리퍼 부품(Moving_Jaw, Wrist_Roll_Follower)은 그대로 두고, 손가락 위에 패드를 씌운 뒤
손가락 뒤쪽을 가로지르는 M2x30 나사 2개로 조여 고정한다. 패드만 풀어서 갈아 끼울 수 있다.

실행 (Windows):
  C:\\Users\\A\\.venvs\\cad\\Scripts\\python make_parts.py
필요 패키지: trimesh manifold3d shapely networkx scipy matplotlib (+ STEP 읽기용 cadquery)

좌표계: 'G' = URDF gripper_link 프레임 (mm). 손가락은 -z 방향, 고정 손가락은 -x 쪽, 움직이는 손가락은 +x 쪽.
원래 부품 형상은 lerobot/SO-ARM100 STEP 파일에서 읽는다 (URDF 메시와 좌표 동일함을 확인).
"""
from pathlib import Path

import numpy as np
import trimesh
from trimesh.transformations import euler_matrix, rotation_matrix, translation_matrix

HERE = Path(__file__).parent
OUT = HERE / "stl"
STEP_DIR = Path(r"C:\Users\A\lerobot\SO-ARM100\STEP\SO101\Follower_Specific")

# ---------------- 설계 값 (여기만 바꾸면 됨) ----------------
PAD_HALF_WIDTH = 20.0  # 패드 접촉면 폭의 절반 (y). 20 -> 폭 40mm (원래 손가락은 끝쪽 9~20mm)
SLEEVE_HALF = 15.0  # 나사가 지나가는 옆벽 바깥면 위치 (y). 15 -> 30mm = M2x30 나사 길이와 같음
MIN_FACE_T = 2.0  # 손가락 끝에서 패드 출력면까지 최소 두께
RUBBER_T = 1.0  # 접촉면에 붙일 고무판 두께. 출력면을 이만큼 뒤로 물려서, 고무 겉면끼리 평행하게 맞닿게 함 (0이면 고무 없음 + 미끄럼 홈)
CLEARANCE = 0.25  # 손가락과 패드 사이 틈 (FDM 기준. 빡빡하면 0.3~0.35)
PAD_TOP_Z = -48.0  # 패드 윗면 (이보다 위는 그리퍼 몸통)
FLOOR_T = 2.5  # 손가락 끝을 받치는 바닥 두께 (패드가 위로 밀려 올라가는 것 방지)
SCREW_Z = (-57.0, -82.0)  # 나사 높이 2곳
SCREW_BACK_GAP = 2.8  # 손가락 뒷면에서 나사 중심까지
M2_CLEAR_R = 1.2  # M2 관통 구멍 반지름 (지름 2.4)
M2_NUT_AF = 4.3  # M2 너트 육각 맞변 거리 (규격 4.0 + 여유)
M2_NUT_DEPTH = 1.8
GROOVE_PITCH, GROOVE_W, GROOVE_D = 3.0, 1.2, 0.5  # 접촉면 미끄럼 방지 홈 (손가락 길이 방향)
STEM_GROOVE_R, STEM_GROOVE_D = 3.0, 1.2  # stemV 패드: 줄기가 눕는 가로 홈 반지름 / 깊이
STEM_GROOVE_Z = -88.0  # V패드: 가로 홈 높이 (G 프레임)

# 꽃병
HOLDER_BASE_R, HOLDER_BASE_H = 40.0, 6.0  # 바닥 지름 80mm
HOLDER_TUBE_R = 11.0  # 기둥 바깥 반지름
HOLDER_HOLE_R = 6.0  # 꽂는 구멍 반지름 (내경 12mm: 줄기 4~10mm)
HOLDER_H = 80.0  # 전체 높이
HOLDER_FUNNEL_R, HOLDER_FUNNEL_H = 16.0, 14.0  # 깔때기 입구 반지름(내경 32mm) / 깔때기 깊이
HOLDER_FLOOR = 3.0  # 구멍 바닥 두께
ROW_N, ROW_PITCH = 3, 70.0  # 3구 꽃병: 개수 / 구멍 사이 간격 (mm)
ROW_DEPTH = 70.0  # 3구 꽃병 바닥 폭 (앞뒤)
ARC_R = 250.0  # 호 3구 꽃병: 호의 반지름 (호 중심 = 로봇 베이스 쪽에 두면 세 꽃까지 거리가 같음)
ARC_PITCH = 85.0  # 호 3구 꽃병: 구멍 중심 사이 직선 거리


def rpy(r, p, y):
    return euler_matrix(r, p, y, "sxyz")


T_FIXED = translation_matrix([0, -0.218214, 0.949706]) @ rpy(-np.pi, 0, 0)


def t_moving(q):
    return (
        translation_matrix([20.2, 18.8, -23.4])
        @ rpy(1.5708, 0, 0)
        @ rotation_matrix(q, [0, 0, 1])
        @ translation_matrix([0, 0, 18.9])
    )


def load_step(name):
    cache = OUT / f"_orig_{name}.stl"
    if not cache.exists():
        import cadquery as cq

        cq.exporters.export(cq.importers.importStep(str(STEP_DIR / f"{name}.step")), str(cache), tolerance=0.05)
    m = trimesh.load(cache)
    return max(m.split(only_watertight=False), key=lambda p: len(p.faces))  # STEP 변환 때 생기는 떠도는 삼각형 제거


def box(x0, x1, y0, y1, z0, z1):
    b = trimesh.creation.box(extents=[x1 - x0, y1 - y0, z1 - z0])
    b.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
    return b


def union(ms):
    return trimesh.boolean.union(ms, engine="manifold")


def diff(a, bs):
    return trimesh.boolean.difference([a] + list(bs), engine="manifold")


def inter(a, b):
    return trimesh.boolean.intersection([a, b], engine="manifold")


def swept_cavity(finger, direction):
    """손가락 + 틈새를 'direction'(패드가 손가락에서 빠지는 방향) 쪽으로 쓸어낸 공간.
    패드를 반대 방향으로 밀어 넣으면 손가락이 걸리지 않고 들어간다."""
    c = CLEARANCE
    grown = union([finger.copy().apply_translation(v) for v in
                   [(0, 0, 0), (0, c, 0), (0, -c, 0), (0, 0, c), (0, 0, -c), (-direction * c, 0, 0)]])
    return union([grown.copy().apply_translation([direction * t, 0, 0]) for t in np.arange(0, 42, 1.5)])


def back_x(finger, z, side):
    """높이 z에서 손가락 뒷면 x (side=-1: 고정 손가락, 뒤가 -x / +1: 움직이는 손가락, 뒤가 +x)"""
    v = finger.vertices[np.abs(finger.vertices[:, 2] - z) < 1.5]
    return v[:, 0].min() if side < 0 else v[:, 0].max()


def hex_prism(af, h, axis_y_center, x, z):
    r = af / np.sqrt(3)  # 꼭짓점 반지름
    p = trimesh.creation.cylinder(radius=r, height=h, sections=6)
    p.apply_transform(rotation_matrix(np.pi / 2, [1, 0, 0]))  # z축 -> y축
    p.apply_translation([x, axis_y_center, z])
    return p


def make_pad(finger, x_face, side, stem_groove):
    """side=-1: 고정 손가락용 (접촉면이 +x를 봄) / side=+1: 움직이는 손가락용 (접촉면이 -x를 봄).
    finger, 반환값 모두 '닫힌 자세' G 프레임."""
    zmin = finger.bounds[0, 2] - FLOOR_T
    # 패드는 뒤가 열린 U자. 안쪽(상대 손가락 쪽)에서 바깥으로 밀어 끼우고, 손가락 뒤를 가로지르는 나사로 잠금
    back_far = min(back_x(finger, z, side) for z in SCREW_Z) if side < 0 else max(back_x(finger, z, side) for z in SCREW_Z)

    # 몸통: 접촉면 ~ 손가락 뒤 + 나사 자리
    xb = back_far + side * (SCREW_BACK_GAP + M2_CLEAR_R + 2.2)
    lo, hi = sorted([x_face, xb])
    body = box(lo, hi, -SLEEVE_HALF, SLEEVE_HALF, zmin, PAD_TOP_Z)
    # 뒤쪽은 손가락 뒷면 경사를 따라 깎아서 무게 줄이기.
    # 절단 평면은 두 나사 중심에서 SCREW_WALL 만큼 바깥을 지나게 -> 두 나사 모두 벽 안에 남음
    # (예전엔 손가락 뒷면 두 점으로 잡아서, 움직이는 쪽 손가락은 뒷면이 휘어 있어 나사 하나가 잘려 나갔음)
    SCREW_WALL = M2_CLEAR_R + 2.8
    (z1, z2) = SCREW_Z
    sx = [back_x(finger, z, side) + side * SCREW_BACK_GAP for z in SCREW_Z]
    p0 = np.array([sx[0] + side * SCREW_WALL, 0, z1])
    p1 = np.array([sx[1] + side * SCREW_WALL, 0, z2])
    t = p1 - p0
    n = np.cross(t, [0, 1, 0])
    n = n / np.linalg.norm(n)
    if np.dot(n, [side, 0, 0]) < 0:
        n = -n
    body = body.slice_plane(p0, -n, cap=True)

    # 넓은 접촉판
    plate_t = 4.0
    plo, phi = sorted([x_face, x_face + side * plate_t])
    plate = box(plo, phi, -PAD_HALF_WIDTH, PAD_HALF_WIDTH, zmin, PAD_TOP_Z)
    pad = union([body, plate])

    # 손가락 자리: 뒤쪽으로 쓸어낸 공간 -> 패드 뒤가 열려 있어서 안쪽에서 밀어 끼울 수 있음
    cav = swept_cavity(finger, direction=side)
    cuts = [cav]

    # 나사 구멍 + 너트 자리 (+y 쪽 머리, -y 쪽 너트)
    for z in SCREW_Z:
        x = back_x(finger, z, side) + side * (SCREW_BACK_GAP)
        hole = trimesh.creation.cylinder(radius=M2_CLEAR_R, height=2 * SLEEVE_HALF + 10, sections=24)
        hole.apply_transform(rotation_matrix(np.pi / 2, [1, 0, 0]))
        hole.apply_translation([x, 0, z])
        cuts.append(hole)
        cuts.append(hex_prism(M2_NUT_AF, 2 * M2_NUT_DEPTH, -SLEEVE_HALF, x, z))

    # 접촉면 미끄럼 방지 홈 (z 방향으로 길게 = 줄기가 y 방향으로 미끄러지는 것 막음). 고무판을 붙이면 필요 없음
    gz0, gz1 = zmin + 1.5, PAD_TOP_Z - 1.5
    for y in (np.arange(-PAD_HALF_WIDTH + 2.5, PAD_HALF_WIDTH - 2.4, GROOVE_PITCH) if RUBBER_T <= 0 else []):
        glo, ghi = sorted([x_face, x_face + side * GROOVE_D])
        cuts.append(box(glo - 0.01 * side, ghi, y - GROOVE_W / 2, y + GROOVE_W / 2, gz0, gz1))

    if stem_groove:  # 줄기(y 방향)가 눕는 반원 홈
        g = trimesh.creation.cylinder(radius=STEM_GROOVE_R, height=2 * PAD_HALF_WIDTH + 2, sections=32)
        g.apply_transform(rotation_matrix(np.pi / 2, [1, 0, 0]))
        depth = STEM_GROOVE_D + RUBBER_T  # 고무판이 홈 안으로 눌려 들어가도 홈 모양이 남게
        g.apply_translation([x_face - side * (STEM_GROOVE_R - depth), 0, STEM_GROOVE_Z])  # 출력면 바깥에 중심 -> 깊이 depth만 파임
        cuts.append(g)

    return diff(pad, cuts)


def flower_holder():
    """꽃 한 송이를 수직으로 세우는 꽃병. 깔때기 입구라 줄기를 꽂기 쉬움 (나중에 로봇 꽂기 목표로도 사용)."""
    # 회전 단면 (반지름 r, 높이 z). 축 위에서 시작해서 축 위에서 끝나야 닫힌 입체가 됨
    prof = [
        (0, 0), (HOLDER_BASE_R, 0), (HOLDER_BASE_R, HOLDER_BASE_H), (HOLDER_TUBE_R, HOLDER_BASE_H),
        (HOLDER_TUBE_R, HOLDER_H - HOLDER_FUNNEL_H), (HOLDER_FUNNEL_R + 2.5, HOLDER_H),
        (HOLDER_FUNNEL_R, HOLDER_H), (HOLDER_HOLE_R, HOLDER_H - HOLDER_FUNNEL_H),
        (HOLDER_HOLE_R, HOLDER_FLOOR), (0, HOLDER_FLOOR),
    ]
    body = trimesh.creation.revolve(np.array(prof, dtype=float), sections=128)
    if body.volume < 0:
        body.invert()
    # 보강 리브 4개 (삼각형)
    from shapely.geometry import Polygon

    tri = Polygon([(HOLDER_TUBE_R - 1, HOLDER_BASE_H - 0.5), (HOLDER_BASE_R - 6, HOLDER_BASE_H - 0.5),
                   (HOLDER_TUBE_R - 1, HOLDER_BASE_H + 25)])
    ribs = []
    for k in range(4):
        r = trimesh.creation.extrude_polygon(tri, height=3.0)  # xy 평면 삼각형을 z로 3mm
        r.apply_translation([0, 0, -1.5])
        r.apply_transform(rotation_matrix(np.pi / 2, [1, 0, 0]))  # (x, y) -> (x, z)
        r.apply_transform(rotation_matrix(k * np.pi / 2 + np.pi / 4, [0, 0, 1]))
        ribs.append(r)
    body = union([body] + ribs)
    # 바닥 무게추 홈 (동전/너트/모래를 넣고 테이프로 막기)
    pocket = trimesh.creation.annulus(r_min=HOLDER_TUBE_R + 2, r_max=HOLDER_BASE_R - 5, height=3.5, sections=96)
    pocket.apply_translation([0, 0, 3.5 / 2 - 0.01])
    return diff(body, [pocket])


def _tube_with_funnel():
    """바닥판 없는 기둥+깔때기 (단면 회전)."""
    prof = [
        (0, 0), (HOLDER_TUBE_R, 0), (HOLDER_TUBE_R, HOLDER_H - HOLDER_FUNNEL_H),
        (HOLDER_FUNNEL_R + 2.5, HOLDER_H), (HOLDER_FUNNEL_R, HOLDER_H),
        (HOLDER_HOLE_R, HOLDER_H - HOLDER_FUNNEL_H), (HOLDER_HOLE_R, HOLDER_FLOOR), (0, HOLDER_FLOOR),
    ]
    t = trimesh.creation.revolve(np.array(prof, dtype=float), sections=128)
    if t.volume < 0:
        t.invert()
    return t


def _ribs(cx, cy, reach):
    from shapely.geometry import Polygon

    tri = Polygon([(HOLDER_TUBE_R - 1, HOLDER_BASE_H - 0.5), (reach, HOLDER_BASE_H - 0.5),
                   (HOLDER_TUBE_R - 1, HOLDER_BASE_H + 25)])
    ribs = []
    for k in range(4):
        r = trimesh.creation.extrude_polygon(tri, height=3.0)
        r.apply_translation([0, 0, -1.5])
        r.apply_transform(rotation_matrix(np.pi / 2, [1, 0, 0]))
        r.apply_transform(rotation_matrix(k * np.pi / 2 + np.pi / 4, [0, 0, 1]))
        r.apply_translation([cx, cy, 0])
        ribs.append(r)
    return ribs


def flower_holder_row():
    """꽃병 3개를 한 줄로 이은 것. 구멍 간격 ROW_PITCH. 바닥 윗면에 칸 번호 점(1~3개) 표시."""
    from shapely.geometry import box as sbox

    length = (ROW_N - 1) * ROW_PITCH + ROW_DEPTH
    plate = sbox(-length / 2, -ROW_DEPTH / 2, length / 2, ROW_DEPTH / 2).buffer(-8).buffer(8)  # 모서리 둥글게
    base = trimesh.creation.extrude_polygon(plate, height=HOLDER_BASE_H)
    xs = [(i - (ROW_N - 1) / 2) * ROW_PITCH for i in range(ROW_N)]
    parts = [base]
    reach = min(HOLDER_BASE_R, ROW_DEPTH / 2) - 6
    for x in xs:
        parts.append(_tube_with_funnel().apply_translation([x, 0, 0]))
        parts += _ribs(x, 0, reach)
    body = union(parts)
    cuts = []
    for i, x in enumerate(xs):
        hole = trimesh.creation.cylinder(radius=HOLDER_HOLE_R, height=HOLDER_H, sections=64)
        hole.apply_translation([x, 0, HOLDER_FLOOR + HOLDER_H / 2])
        cuts.append(hole)  # 리브가 구멍을 막지 않게 다시 뚫기
        pocket = trimesh.creation.annulus(r_min=HOLDER_TUBE_R + 2, r_max=min(ROW_PITCH, ROW_DEPTH) / 2 - 5,
                                          height=3.5, sections=96)
        pocket.apply_translation([x, 0, 3.5 / 2 - 0.01])
        cuts.append(pocket)
        for k in range(i + 1):  # 칸 번호 점: 앞쪽(-y)에 1~3개
            dot = trimesh.creation.cylinder(radius=2.0, height=2.0, sections=24)
            dot.apply_translation([x + (k - i / 2) * 6, -ROW_DEPTH / 2 + 7, HOLDER_BASE_H])
            cuts.append(dot)
    return diff(body, cuts)


def flower_holder_arc():
    """꽃병 3개를 호(원호) 위에 놓은 것. 호의 중심은 -y 쪽(로봇 쪽) ARC_R 거리.
    가운데 구멍이 원점, 구멍 중심 사이 직선 거리 = ARC_PITCH."""
    from shapely.geometry import Polygon

    step = 2 * np.arcsin(ARC_PITCH / 2 / ARC_R)  # 구멍 사이 각도
    angs = [(i - (ROW_N - 1) / 2) * step for i in range(ROW_N)]
    pos = [(ARC_R * np.sin(a), ARC_R * np.cos(a) - ARC_R) for a in angs]
    half_w = ROW_DEPTH / 2
    a_end = abs(angs[0]) + (half_w - 4) / ARC_R  # 양 끝 여유
    ts = np.linspace(-a_end, a_end, 120)
    outer = [((ARC_R + half_w) * np.sin(t), (ARC_R + half_w) * np.cos(t) - ARC_R) for t in ts]
    inner = [((ARC_R - half_w) * np.sin(t), (ARC_R - half_w) * np.cos(t) - ARC_R) for t in ts[::-1]]
    plate = Polygon(outer + inner).buffer(-8).buffer(8)  # 모서리 둥글게
    base = trimesh.creation.extrude_polygon(plate, height=HOLDER_BASE_H)
    parts = [base]
    reach = min(HOLDER_BASE_R, half_w) - 6
    for (x, y), a in zip(pos, angs):
        parts.append(_tube_with_funnel().apply_translation([x, y, 0]))
        for r in _ribs(0, 0, reach):
            r.apply_transform(rotation_matrix(-a, [0, 0, 1]))
            parts.append(r.apply_translation([x, y, 0]))
    body = union(parts)
    cuts = []
    for i, ((x, y), a) in enumerate(zip(pos, angs)):
        hole = trimesh.creation.cylinder(radius=HOLDER_HOLE_R, height=HOLDER_H, sections=64)
        hole.apply_translation([x, y, HOLDER_FLOOR + HOLDER_H / 2])
        cuts.append(hole)
        pocket = trimesh.creation.annulus(r_min=HOLDER_TUBE_R + 2, r_max=min(ARC_PITCH, ROW_DEPTH) / 2 - 5,
                                          height=3.5, sections=96)
        pocket.apply_translation([x, y, 3.5 / 2 - 0.01])
        cuts.append(pocket)
        # 칸 번호 점: 로봇 쪽(호 안쪽) 가장자리에 1~3개, 호 방향으로 나란히
        rr = ARC_R - half_w + 7
        for k in range(i + 1):
            t = a + (k - i / 2) * 6 / rr
            dot = trimesh.creation.cylinder(radius=2.0, height=2.0, sections=24)
            dot.apply_translation([rr * np.sin(t), rr * np.cos(t) - ARC_R, HOLDER_BASE_H])
            cuts.append(dot)
    return diff(body, cuts)


def main():
    OUT.mkdir(exist_ok=True)
    fixed_l = load_step("Wrist_Roll_Follower_SO101")
    moving_l = load_step("Moving_Jaw_SO101")

    fixed_g = fixed_l.copy().apply_transform(T_FIXED)
    fixed_finger = inter(fixed_g, box(-80, 80, -80, 80, -200, -47))
    x_face = fixed_finger.bounds[1, 0] + MIN_FACE_T + RUBBER_T  # 고무 겉면 위치 (고무끼리 여기서 맞닿음)

    finger_l = inter(moving_l, box(-80, 80, -200, -24, -80, 80))  # 움직이는 손가락 (로컬)
    q_c = None
    for q in np.arange(-0.2, 0.0, 0.0025):
        if finger_l.copy().apply_transform(t_moving(q)).bounds[0, 0] >= x_face + RUBBER_T + MIN_FACE_T:
            q_c = q
            break
    T_c = t_moving(q_c)
    moving_finger = finger_l.copy().apply_transform(T_c)
    print(f"고무 겉면 x={x_face:.2f}mm (고무 {RUBBER_T}mm), 패드끼리 닿는 각도 q={q_c:.4f}rad ({np.degrees(q_c):.1f}도), 원래 손가락 끝 맞닿음 약 -11.3도")

    results = {}
    for variant, groove in [("flat", False), ("stemV", True)]:
        pf = make_pad(fixed_finger, x_face - RUBBER_T, -1, groove)  # 출력면은 고무 두께만큼 뒤로
        pm = make_pad(moving_finger, x_face + RUBBER_T, +1, groove)
        # 부품 좌표(원래 STEP 좌표)로 되돌림 -> 조립 확인용
        pf_l = pf.copy().apply_transform(np.linalg.inv(T_FIXED))
        pm_l = pm.copy().apply_transform(np.linalg.inv(T_c))
        results[variant] = (pf, pm, pf_l, pm_l)
        # 출력용: 접촉면이 바닥(z=0)에 닿게 눕힘
        for name, mesh_g, side in [("fixed", pf, -1), ("moving", pm, +1)]:
            m = mesh_g.copy()
            R =rotation_matrix(-side * np.pi / 2, [0, 1, 0])  # 접촉면 법선 -> -z (접촉면이 베드에 닿게)
            m.apply_transform(R)
            m.apply_translation(-m.bounds[0])
            m.export(OUT / f"pad_{variant}_{name}.stl")
            print(f"pad_{variant}_{name}.stl  크기 {np.round(m.extents, 1)} mm  부피 {m.volume / 1000:.1f} cm3  watertight={m.is_watertight}")

    holder = flower_holder()
    holder.export(OUT / "flower_holder.stl")
    print(f"flower_holder.stl  크기 {np.round(holder.extents, 1)} mm  watertight={holder.is_watertight}")
    row = flower_holder_row()
    row.export(OUT / "flower_holder_x3.stl")
    print(f"flower_holder_x3.stl  크기 {np.round(row.extents, 1)} mm  watertight={row.is_watertight}")
    arc = flower_holder_arc()
    arc.export(OUT / "flower_holder_arc3.stl")
    print(f"flower_holder_arc3.stl  크기 {np.round(arc.extents, 1)} mm  watertight={arc.is_watertight}")

    # 간섭 검사: 패드 포함 움직이는 쪽 vs 고정 쪽, 닫힘~열림 전 범위
    pf, pm, pf_l, pm_l = results["flat"]
    fixed_all = union([fixed_g, pf])
    cm = trimesh.collision.CollisionManager()
    cm.add_object("fixed", fixed_all)
    worst = []
    for q in np.linspace(q_c + 0.01, 1.745, 40):
        mv = union([moving_l, pm_l]).apply_transform(t_moving(q))
        worst.append((cm.min_distance_single(mv), q))
    d, q = min(worst)
    print(f"간섭 검사 (q {q_c + 0.01:.3f}~1.745): 최소 거리 {d:.2f}mm @ q={q:.3f}")
    # 패드-손가락 간섭 (끼웠을 때 겹치면 안 됨)
    print("패드-손가락 겹침 부피(고정, 움직임):",
          round(inter(pf, fixed_finger).volume, 2), round(inter(pm, moving_finger).volume, 2))


if __name__ == "__main__":
    main()
