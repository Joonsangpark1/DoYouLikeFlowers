"""스크립트 집기·넣기 (11-25): 고정 꽃병 칸 → 잡기 → 수직으로 뽑기 → 통 위 → 놓기. HIL-SERL 정책 전의 기본 동작이자 폴백.

순서: 그리퍼 열기(OPEN) → 줄기 앞 pre_back(3 cm) → 줄기 점까지 직선 접근 → 닫기(CLOSE) → 잡힘 확인(덜 닫힘 = 줄기)
      → 수직 LIFT_M(9 cm) 들기 → 통 위 자세(configs/bin_pose.json) → 놓기 → 시작 자세
칸 좌표·보정 = configs/slot_targets.json (flower_pick_actor.fixed_slot_point/q). 통 자세는 --record-bin 으로 손으로 옮겨 저장.

사용 (WSL, 로봇 연결, 꽃 꽂힌 상태):
  python scripted_pick.py --record-bin          # 5초 뒤 힘 빠짐 → 팔을 손으로 통 위(놓을 자리)에 → Enter 저장
  python scripted_pick.py --slot 2              # 2번 칸 꽃 집어서 통에
  python scripted_pick.py --slot 2 --no-bin     # 뽑기까지만 (들고 있다가 Enter 누르면 그 자리에서 놓음)
함수: ScriptedPicker(robot, names).pick_place(slot, step_cb) — executor가 사용
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

import record_prior as RP
from flower_pick_actor import fixed_slot_point, fixed_slot_q
from teleop_wrist import WristIK

HERE = Path(__file__).resolve().parent
OPEN, CLOSE = 69.0, 100.0          # 그리퍼 (0 끝까지 열림 ~ 100 닫힘). 11-25 사용자: 접근은 35° 열림 = 69
HOLD_MIN, HOLD_MAX = 72.0, 96.0    # 닫은 뒤 실측이 이 사이면 줄기를 잡은 것 (끝까지 닫히면 빈손, 열림 69보다는 더 닫혀야)
LIFT_M = 0.09                      # 줄기 꽂힌 깊이 8.5 cm + 여유
BIN_FILE = HERE / "configs/bin_pose.json"


class ScriptedPicker:
    def __init__(self, robot, names):
        self.robot, self.names = robot, names
        ik_cfg = json.loads((HERE / "configs/flower_hil.json").read_text())["env"]["processor"]["inverse_kinematics"]
        self.ik = WristIK(str(HERE / ik_cfg["urdf_path"]), ik_cfg["target_frame_name"], names, np.full(6, -180.0), np.full(6, 180.0))
        for i, n in enumerate(names):
            try:
                jl = self.ik.kin.robot.get_joint_limits(n); self.ik.lo[i], self.ik.hi[i] = np.degrees(jl[0]) + 1, np.degrees(jl[1]) - 1
            except Exception:
                pass
        self.fixed = json.loads((HERE / "configs/slot_targets.json").read_text())
        self.poses = json.loads((HERE / "stereo/slot_poses.json").read_text())["slots"]
        self.start = json.loads((RP.SMOLVLA_CODE / "start_pose_vla_trial4.json").read_text())

    def q(self):
        return RP.read_q(self.robot, self.names)

    def go(self, q, grip=None, fps=30):
        q = np.array(q, float)
        if grip is not None:
            q[5] = grip
        RP.move_smooth(self.robot, dict(zip(self.names, q.tolist())), fps=fps)

    def grip(self, value):
        cur = self.q(); cur[5] = value
        RP.move_smooth(self.robot, dict(zip(self.names, cur.tolist())))
        time.sleep(0.4)
        return float(self.q()[5])

    # ---------- 궤적 (11-25: 관절 한꺼번에 보간하면 끝단이 휘어 옆 꽃·꽃병을 칠 수 있음 → 끝단 직선) ----------
    def line_to(self, p_tcp, pitch, step_m=0.005, dt=0.035):
        """그리퍼 중심(TCP)을 지금 위치에서 p_tcp 까지 직선으로 (5 mm 간격 IK). 숙임도 지금 값 → pitch 로 서서히.
        11-25 실물: 숙임을 처음부터 목표값으로 고정하면 시작 자세(손목 각도가 크게 다름) 근처에서 IK가 7 mm 못 닿음 → 숙임 보간 + 안 풀리면 반복 늘려 재시도"""
        tcp = np.array(json.loads((HERE / "stereo/stereo_config.json").read_text()).get("tcp_offset_m", [0, 0, 0]), float)
        q = self.q(); T = self.ik.fk(q); p0 = T[:3, 3] + T[:3, :3] @ tcp
        pitch0 = self.ik.pose(q)[1]
        n = max(1, int(np.ceil(max(np.linalg.norm(p_tcp - p0) / step_m, abs(pitch - pitch0) / 3.0))))  # 숙임은 한 단계 3° 이하
        for k in range(1, n + 1):
            pk = p0 + (p_tcp - p0) * k / n
            ptk = pitch0 + (pitch - pitch0) * k / n
            qs = q.copy()
            for iters in (40, 40, 150):
                qs, perr, _ = self.ik.solve(qs, pk - self.ik.fk(qs)[:3, :3] @ tcp, ptk, iters=iters)
                if perr < 0.002:
                    break
            if perr > 0.005:
                raise RuntimeError(f"직선 이동 IK 실패 ({perr * 1000:.1f} mm) at {np.round(pk * 1000)} 숙임 {ptk:.0f}°")
            qs[5] = q[5]
            self.robot.bus.sync_write("Goal_Position", dict(zip(self.names, qs.tolist())))
            time.sleep(dt); q = qs
        time.sleep(0.3)
        return q

    def lift_straight(self, dz):
        """끝단을 수직으로 dz 만큼 (숙임 유지)"""
        q = self.q(); p, pitch = self.ik.pose(q)
        return self.line_to(p + np.array([0, 0, dz]), pitch)

    def pan_only(self, pan_deg):
        q = self.q(); q[0] = pan_deg
        self.go(q)

    def approach(self, slot: int, back_m: float = 0.0, step_cb=print, grip=None):
        """시작 자세 → 어깨만 칸 방향 → 줄기에서 far_m 앞(잡는 높이)까지 직선 → back_m 까지 칸 방향 직선. 반환: (p_stem, u, pitch)"""
        P = self.poses[str(slot)]
        p_stem, u = fixed_slot_point(self.fixed, slot)
        q_pre = fixed_slot_q(self.ik, self.fixed, slot, np.array(P["arrive_q"]), P["pitch_deg"], back_m=self.fixed.get("pre_back_m", 0.03))
        pitch = self.ik.pose(q_pre)[1]  # 닿는 숙임 (시연값에서 조정됐을 수 있음)
        far = self.fixed.get("far_back_m", 0.08)
        if grip is not None:
            self.grip(grip)
        step_cb(f"turn to slot{slot}")
        self.pan_only(q_pre[0])
        step_cb(f"down to {far * 100:.0f}cm before stem")
        self.line_to(p_stem - u * far, pitch, step_m=0.008)
        step_cb(f"straight in to {back_m * 100:.0f}cm")
        self.line_to(p_stem - u * back_m, pitch)
        return p_stem, u, pitch

    def pick_place(self, slot: int, step_cb=print, to_bin: bool = True) -> dict:
        p_stem, u, pitch = self.approach(slot, 0.0, step_cb, grip=OPEN)
        step_cb("close gripper")
        g = self.grip(CLOSE)
        held = HOLD_MIN < g < HOLD_MAX
        if held:  # 줄기에 막혀 멈춘 상태로 계속 100을 밀면 모터 과부하 → 실측보다 조금 더 닫은 값으로 유지
            self.grip(min(CLOSE, g + 4))
        res = {"slot": slot, "grip_after_close": round(g, 1), "held": held}
        if not held:
            step_cb(f"NOT HELD (grip {g:.0f})")
            self.grip(OPEN)
            self.line_to(p_stem - u * self.fixed.get("far_back_m", 0.08), pitch)
            return res
        step_cb(f"pull up {LIFT_M * 100:.0f}cm (grip {g:.0f})")
        self.lift_straight(LIFT_M)
        step_cb("back off 5cm")
        q = self.q(); p, _ = self.ik.pose(q)
        self.line_to(p - u * 0.05, pitch)
        g2 = float(self.q()[5]); res["grip_after_lift"] = round(g2, 1)
        res["held_after_lift"] = HOLD_MIN < g2 < HOLD_MAX
        if to_bin and BIN_FILE.exists():
            b = json.loads(BIN_FILE.read_text()); qb = np.array([b[n] for n in self.names])
            step_cb("turn to bin")
            self.pan_only(qb[0])
            step_cb("over bin")
            self.go(qb, grip=g2)
            step_cb("release")
            self.grip(OPEN)
        res["placed"] = bool(to_bin and BIN_FILE.exists())
        return res

    def home(self):
        self.go(np.array([self.start[n] for n in self.names]), grip=self.q()[5])


def record_bin(robot, names):
    print("5초 뒤 모터 힘이 빠집니다. 팔을 손으로 받치세요.")
    for s in range(5, 0, -1):
        print(f"  {s}"); time.sleep(1)
    robot.bus.disable_torque()
    input("팔을 통 위(꽃을 떨어뜨릴 자리)로 옮기고 Enter")
    q = RP.read_q(robot, names)
    RP.hold_here(robot)
    BIN_FILE.write_text(json.dumps({n: round(float(v), 2) for n, v in zip(names, q)}, indent=2))
    print("저장", BIN_FILE, np.round(q, 1))


if __name__ == "__main__":
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=int, choices=[1, 2, 3])
    ap.add_argument("--record-bin", action="store_true")
    ap.add_argument("--no-bin", action="store_true")
    a = ap.parse_args()
    rcfg = json.loads((HERE / "configs/flower_hil.json").read_text())["env"]["robot"]
    robot = SO101Follower(SO101FollowerConfig(port=RP.by_id("/dev/serial/by-id/usb-1a86_*", rcfg["port"]), id=rcfg["id"],
                                              max_relative_target=10.0, disable_torque_on_disconnect=False))
    robot.connect(); names = list(robot.bus.motors)
    try:
        if a.record_bin:
            record_bin(robot, names)
        elif a.slot:
            pk = ScriptedPicker(robot, names)
            print(f"전압 {RP.read_volt(robot)} V")
            if input(f"{a.slot}번 칸 꽃을 집습니다{'' if a.no_bin else ' → 통에 넣기'}. 진행? [y/N] ").lower() == "y":
                pk.home()
                r = pk.pick_place(a.slot, step_cb=lambda m: print("  >", m), to_bin=not a.no_bin)
                print("결과:", r)
                if a.no_bin and r.get("held"):
                    input("Enter = 그 자리에서 놓기"); pk.grip(OPEN)
                pk.home()
    finally:
        RP.hold_here(robot); robot.disconnect()
