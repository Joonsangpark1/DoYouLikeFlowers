"""녹화한 에피소드 하나를 MuJoCo로 재생해서 이미지로 남기기 (시뮬 장면 확인용, 1회성).

장면: SO-101 (MuJoCo Menagerie, 손목 카메라 포함) + 1구 꽃병 3개 + 꽃 3송이 (줄기 + 머리).
관절: 데이터셋 observation.state (도, 그리퍼 0~100)를 그대로 qpos로 넣음 (물리 없이 자세만).
꽃병 위치: 실제 데이터 도착 위치(FK) 기준 추정 — 칸 방향은 도착 방향, 거리는 도착 거리 + 5 cm. 실측 아님.

사용 (Windows, so101 venv):
  python sim_replay.py D:\\data\\flower\\sim\\ep143
출력: <prefix>_sim_montage.png (행 = 시점, 열 = 실제 손목 카메라 / 시뮬 손목 카메라 / 시뮬 외부 시점)
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw

SO101 = Path(r"C:\Users\A\Desktop\로보틱스2\gaze_grasp\assets\so101")
ARM = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
# 칸별 꽃병 위치 (로봇 베이스 기준 m). 도착 위치 평균 (1번칸 y+3.5, 2번칸 −2, 3번칸 −7 cm, x 18~22 cm)에서 바깥으로 5 cm
SLOT_ARRIVAL = {1: (0.195, 0.035), 2: (0.205, -0.020), 3: (0.180, -0.070)}
FLOWER_RGBA = {"rose": "0.95 0.45 0.6 1", "blue": "0.35 0.55 0.95 1", "sunflower": "1 0.8 0.15 1"}
VASE_R, VASE_H, STEM_TOP, HEAD_R = 0.028, 0.08, 0.30, 0.035   # 꽃병은 실물(바닥 80 mm)보다 가늘게: 추정 칸 간격(약 7 cm)에서 안 겹치게
CAM_ROLL_DEG, CAM_FOVY = 90.0, 60.0   # Menagerie wrist_cam은 광축 둘레로 90° 돌아가 있음 (바닥이 옆으로 보임) / 실제 카메라에 가깝게 화각 넓힘


def slot_xy(slot):
    x, y = SLOT_ARRIVAL[slot]
    r, th = math.hypot(x, y) + 0.05, math.atan2(y, x)
    return r * math.cos(th), r * math.sin(th)


def build(layout):
    assets = {p.name: p.read_bytes() for p in (SO101 / "assets").glob("*")}
    arm = mujoco.MjSpec.from_string((SO101 / "so101.xml").read_text(encoding="utf-8"), assets)
    vases = []
    for s in (1, 2, 3):
        x, y = slot_xy(s)
        c = FLOWER_RGBA[layout[str(s)]]
        vases.append(f"""
    <body pos="{x:.3f} {y:.3f} 0">
      <geom type="cylinder" size="{VASE_R} {VASE_H / 2}" pos="0 0 {VASE_H / 2}" rgba="0.08 0.08 0.08 1"/>
      <geom type="capsule" fromto="0 0 0.02 0 0 {STEM_TOP}" size="0.004" rgba="0.55 0.75 0.3 1"/>
      <geom type="sphere" size="{HEAD_R}" pos="0 0 {STEM_TOP + 0.02}" rgba="{c}"/>
      <geom type="box" size="0.012 0.004 0.002" pos="0.01 0 {STEM_TOP - 0.08}" euler="0 0.4 0.5" rgba="0.5 0.75 0.3 1"/>
    </body>""")
    world = f"""<mujoco>
  <visual><global offwidth="640" offheight="480"/><quality shadowsize="2048"/></visual>
  <asset><texture name="grid" type="2d" builtin="checker" rgb1="0.82 0.82 0.8" rgb2="0.75 0.75 0.73" width="300" height="300"/>
    <material name="grid" texture="grid" texrepeat="8 8"/></asset>
  <worldbody>
    <light pos="0.3 0 1.2" dir="0 0 -1" diffuse="0.8 0.8 0.8"/>
    <light pos="-0.4 0.4 0.8" dir="0.5 -0.4 -0.6" diffuse="0.4 0.4 0.4"/>
    <geom type="plane" size="0.6 0.6 0.01" material="grid"/>
    <site name="mount" pos="0 0 0"/>
    {''.join(vases)}
  </worldbody>
</mujoco>"""
    spec = mujoco.MjSpec.from_string(world)
    spec.attach(arm, site=spec.site("mount"), prefix="")
    spec.assets = assets
    m = spec.compile()
    cid = m.camera("wrist_cam").id
    qz, q = np.zeros(4), np.zeros(4)
    mujoco.mju_axisAngle2Quat(qz, [0, 0, 1], math.radians(CAM_ROLL_DEG))
    mujoco.mju_mulQuat(q, m.cam_quat[cid].copy(), qz)
    m.cam_quat[cid], m.cam_fovy[cid] = q, CAM_FOVY
    return m


def set_pose(m, d, q):
    for n, v in zip(ARM, q):
        jid = m.joint(n).id
        if n == "gripper":
            lo, hi = m.jnt_range[jid]
            val = lo + (v / 100.0) * (hi - lo)
        else:
            val = math.radians(v)
        d.qpos[m.jnt_qposadr[jid]] = val
    mujoco.mj_forward(m, d)


def main(prefix):
    prefix = Path(prefix)
    meta = json.loads(Path(f"{prefix}_meta.json").read_text(encoding="utf-8"))
    state = np.load(f"{prefix}_state.npy")
    m = build(meta["log"]["layout"])
    d = mujoco.MjData(m)
    r = mujoco.Renderer(m, 480, 640)
    ext = mujoco.MjvCamera()
    ext.type = mujoco.mjtCamera.mjCAMERA_FREE
    ext.lookat[:] = [0.13, 0.0, 0.12]
    ext.azimuth, ext.elevation, ext.distance = 135, -28, 0.85

    tiles = []
    for j in meta["frame_idx"]:
        set_pose(m, d, state[j])
        r.update_scene(d, camera="wrist_cam")
        wrist = Image.fromarray(r.render())
        r.update_scene(d, camera=ext)
        outside = Image.fromarray(r.render())
        real = Image.open(f"{prefix}_real_{j:03d}.png").convert("RGB")
        tiles.append((j, real, wrist, outside))

    W, H, s = 640, 480, 0.5
    w, h = int(W * s), int(H * s)
    canvas = Image.new("RGB", (3 * w, len(tiles) * h + 24), (20, 20, 20))
    dr = ImageDraw.Draw(canvas)
    head = f"ep{meta['episode']}  {meta['task']}  layout 1/2/3 = " + "/".join(meta["log"]["layout"][k] for k in "123")
    dr.text((6, 6), head, fill=(255, 255, 255))
    for row, (j, *imgs) in enumerate(tiles):
        for col, (im, lab) in enumerate(zip(imgs, ("real wrist cam", "sim wrist cam", "sim outside"))):
            canvas.paste(im.resize((w, h)), (col * w, 24 + row * h))
            dr.rectangle([col * w, 24 + row * h, col * w + 150, 24 + row * h + 14], fill=(0, 0, 0))
            dr.text((col * w + 4, 24 + row * h + 2), f"{lab}  t={j}", fill=(255, 255, 0))
    out = Path(f"{prefix}_sim_montage.png")
    canvas.save(out)
    # 마지막 시점 외부 시점은 크게 한 장 더
    tiles[-1][3].save(f"{prefix}_sim_outside_end.png")
    print("saved", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else r"D:\data\flower\sim\ep143")
