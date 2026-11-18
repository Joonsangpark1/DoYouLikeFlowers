"""게임패드로 SO-101 끝단(x/y/z) + 손목 숙임(pitch) + 손목 회전(roll)을 조종한다. 녹화 없음.

lerobot 기본 게임패드 경로(teleop_test.py / record_demos.py)와 다른 점:
  - 목표(끝단 위치·숙임·회전)를 프로그램이 직접 들고 있음. lerobot은 매 스텝 "실제 위치(FK) + 스틱"을 목표로
    잡아서, 모터 지연(약 0.2 s)·중력 처짐만큼 목표가 실제 쪽으로 끌려가며 흘러감
  - IK가 위치 3 + 손목 숙임 1을 같이 맞춤 (lerobot은 방향 가중치 0.01 → 손목 각도가 이동마다 제멋대로 바뀜)
  - 손목 회전(wrist_roll)은 IK에 넣지 않고 스틱으로 직접 (SO-101은 5축이라 회전은 따로 둠)
  - IK가 목표에 못 닿으면(1 cm 넘게 남음) 그 방향 이동을 무시 → 팔이 튀지 않음

조작:
  왼쪽 스틱 위/아래 = 앞/뒤(x)      왼쪽 스틱 좌/우 = 왼쪽/오른쪽(y)
  오른쪽 스틱 위/아래 = 높이(z)      오른쪽 스틱 좌/우 = 손목 회전(roll)
  LB 누른 채 오른쪽 스틱 위/아래 = 손목 숙임(pitch, 위 = 끝이 위로)
  RT(R2) 닫기 / LT(L2) 열기          SELECT(Back) 또는 Ctrl+C 종료 (팔은 마지막 자세 유지)

사용 (Windows에서 gamepad_sender.ps1 켜 둔 상태):
  python teleop_wrist.py
  python teleop_wrist.py --speed 0.05     # 끝단 최대 속도 5 cm/s
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from lerobot.model.kinematics import RobotKinematics
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

from lerobot_plugins import BUTTONS, RemoteGamepad, RemoteGamepadConfig

HERE = Path(__file__).resolve().parent
ARM = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]
IK_JOINTS = [0, 1, 2, 3]  # pan, lift, elbow, wrist_flex (roll은 직접)


class WristIK:
    """위치 3 + 숙임 1 → 관절 4개 (감쇠 최소제곱, 수치 자코비안). 각도 단위 = 도 (lerobot과 같음)."""

    def __init__(self, urdf: str, frame: str, names: list[str], lo: np.ndarray, hi: np.ndarray):
        self.kin = RobotKinematics(urdf, frame, names)
        self.lo, self.hi = lo, hi
        # 접근축(그리퍼가 향하는 방향)의 프레임 로컬 벡터: 모든 관절 0(팔을 앞으로 곧게)에서 +x를 향하는 축
        R0 = self.fk(np.zeros(len(names)))[:3, :3]
        self.a_local = R0.T @ np.array([1.0, 0.0, 0.0])

    def fk(self, q):
        return self.kin.forward_kinematics(np.asarray(q, dtype=float))

    def pose(self, q):
        """(위치 m, 숙임 도). 숙임 = 접근축이 수평에서 위로 몇 도."""
        T = self.fk(q)
        a = T[:3, :3] @ self.a_local
        return T[:3, 3].copy(), math.degrees(math.atan2(a[2], math.hypot(a[0], a[1])))

    def solve(self, q0, p_des, pitch_des, iters=15, damp=0.002, w_pitch=0.002):
        """w_pitch: 숙임 1도를 위치 2 mm와 같은 무게로. damp: 관절이 도 단위라 자코비안이 작음(1도에 약 5 mm) → 감쇠도 작게."""
        q = np.array(q0, dtype=float)
        for _ in range(iters):
            p, pt = self.pose(q)
            err = np.concatenate([p_des - p, [w_pitch * (pitch_des - pt)]])
            if np.linalg.norm(err[:3]) < 5e-4 and abs(pitch_des - pt) < 0.5:
                break
            J = np.zeros((4, len(IK_JOINTS)))
            for c, j in enumerate(IK_JOINTS):
                dq = np.zeros_like(q)
                dq[j] = 0.5
                p2, pt2 = self.pose(q + dq)
                J[:3, c] = (p2 - p) / 0.5
                J[3, c] = w_pitch * (pt2 - pt) / 0.5
            step = J.T @ np.linalg.solve(J @ J.T + damp**2 * np.eye(4), err)
            step = np.clip(step, -5.0, 5.0)  # 한 반복에 5도 넘게 안 움직임
            for c, j in enumerate(IK_JOINTS):
                q[j] = np.clip(q[j] + step[c], self.lo[j], self.hi[j])
        p, pt = self.pose(q)
        return q, float(np.linalg.norm(p_des - p)), abs(pitch_des - pt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=HERE / "configs" / "flower_hil.json")
    ap.add_argument("--hz", type=float, default=30.0)
    ap.add_argument("--speed", type=float, default=0.08, help="끝단 최대 속도 m/s (스틱 끝까지)")
    ap.add_argument("--pitch-speed", type=float, default=45.0, help="손목 숙임 최대 속도 deg/s")
    ap.add_argument("--roll-speed", type=float, default=90.0, help="손목 회전 최대 속도 deg/s")
    ap.add_argument("--grip-speed", type=float, default=80.0, help="그리퍼 속도 (0~100 단위/s)")
    ap.add_argument("--max-joint-step", type=float, default=6.0, help="한 스텝 관절 최대 변화 (도)")
    args = ap.parse_args()

    raw = json.loads(args.config.read_text())
    rcfg, tcfg = raw["env"]["robot"], raw["env"]["teleop"]
    ikcfg = raw["env"]["processor"]["inverse_kinematics"]
    urdf = str(HERE / ikcfg["urdf_path"])

    pad = RemoteGamepad(RemoteGamepadConfig(port=tcfg["port"], deadzone=tcfg["deadzone"],
                                            x_sign=tcfg["x_sign"], y_sign=tcfg["y_sign"], z_sign=tcfg["z_sign"],
                                            swap_gripper=tcfg["swap_gripper"], always_intervene=True))
    robot = SO101Follower(SO101FollowerConfig(port=rcfg["port"], id=rcfg["id"],
                                              disable_torque_on_disconnect=False,
                                              max_relative_target=None, cameras={}))
    pad.connect()
    robot.connect()
    names = list(robot.bus.motors)  # 5 팔 + gripper
    lo = np.full(len(names), -180.0)
    hi = np.full(len(names), 180.0)
    # URDF 관절 범위 (도) — placo 모델에서 읽기
    ik = WristIK(urdf, ikcfg["target_frame_name"], names, lo, hi)
    for i, n in enumerate(names):
        try:
            jl = ik.kin.robot.get_joint_limits(n)
            lo[i], hi[i] = math.degrees(jl[0]) + 1, math.degrees(jl[1]) - 1
        except Exception:
            pass

    obs = robot.get_observation()
    q_cmd = np.array([obs[f"{n}.pos"] for n in names], dtype=float)
    p_cmd, pitch_cmd = ik.pose(q_cmd)
    roll_cmd, grip_cmd = q_cmd[4], q_cmd[5]
    dt = 1.0 / args.hz
    print(f"\n시작 끝단 {np.round(p_cmd, 3)} m, 숙임 {pitch_cmd:.0f}°, 회전 {roll_cmd:.0f}°")
    print("왼쪽 스틱 x/y, 오른쪽 스틱 위아래 z · 좌우 회전, LB+오른쪽 위아래 숙임, RT 닫기/LT 열기, SELECT 종료\n")
    pad.clear_pressed()
    blocked = ""
    try:
        while True:
            t0 = time.perf_counter()
            if pad.pop_pressed("back"):
                break
            s = pad._live_state()
            if s is None:  # 패드 끊김 → 정지 (목표 유지)
                print("\r패드없음 - 정지                                                    ", end="", flush=True)
                time.sleep(dt)
                continue
            dz = lambda v: 0.0 if abs(v) < tcfg["deadzone"] else float(np.clip(v, -1, 1))
            lb = bool(int(s.get("btn", 0)) & BUTTONS["lb"])
            vx = tcfg["x_sign"] * dz(s.get("ly", 0.0))
            vy = tcfg["y_sign"] * -dz(s.get("lx", 0.0))
            ry = dz(s.get("ry", 0.0))
            vz = 0.0 if lb else tcfg["z_sign"] * ry
            vpitch = ry if lb else 0.0
            vroll = dz(s.get("rx", 0.0))
            close, open_ = s.get("rt", 0.0) > 0.5, s.get("lt", 0.0) > 0.5
            if tcfg["swap_gripper"]:
                close, open_ = open_, close

            # 새 목표 → IK. 못 닿으면 위치/숙임 목표는 그대로 두고(그 방향 무시) 관절도 안 바꿈
            p_new = p_cmd + np.array([vx, vy, vz]) * args.speed * dt
            pitch_new = float(np.clip(pitch_cmd + vpitch * args.pitch_speed * dt, -100, 100))
            q_try = q_cmd.copy()
            q_try[4] = roll_cmd
            q_sol, perr, aerr = ik.solve(q_try, p_new, pitch_new)
            if perr < 0.01 and aerr < 5.0 and np.abs(q_sol[:4] - q_cmd[:4]).max() <= args.max_joint_step:
                q_cmd[:4], p_cmd, pitch_cmd, blocked = q_sol[:4], p_new, pitch_new, ""
            elif vx or vy or vz or vpitch:
                blocked = f"  [못 감: 오차 {perr * 100:.1f}cm/{aerr:.0f}°]"
            roll_cmd = float(np.clip(roll_cmd + vroll * args.roll_speed * dt, lo[4], hi[4]))
            q_cmd[4] = roll_cmd
            grip_cmd = float(np.clip(grip_cmd + (close * -1 + open_ * 1) * args.grip_speed * dt, 0, 100))
            q_cmd[5] = grip_cmd

            robot.send_action({f"{n}.pos": float(v) for n, v in zip(names, q_cmd)})
            print(f"\r패드OK{' LB' if lb else '   '}  목표 x={p_cmd[0]:.3f} y={p_cmd[1]:.3f} z={p_cmd[2]:.3f} m  "
                  f"숙임 {pitch_cmd:+5.0f}° 회전 {roll_cmd:+5.0f}° 그리퍼 {grip_cmd:5.1f}{blocked}          ",
                  end="", flush=True)
            time.sleep(max(0.0, dt - (time.perf_counter() - t0)))
    except KeyboardInterrupt:
        pass
    finally:
        print("\n종료 (팔은 마지막 자세 유지)")
        pad.disconnect()
        robot.disconnect()


if __name__ == "__main__":
    main()
