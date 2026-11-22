"""HIL-SERL 액션 [dx, dy, dz, droll, gripper] → SO-101 관절 목표. 시연 녹화(record_prior.py)와 나중의 actor가 같이 쓴다.

lerobot 공식 EE 파이프라인은 [dx, dy, dz, gripper]만 받고 손목 방향은 못 바꿈 → 줄기 잡는 방향을 맞추려고 회전 1축 추가 (11-17).
동작은 teleop_wrist.py와 같음:
  - 목표(끝단 위치·숙임·회전)를 이 객체가 들고 있음 (매 스텝 FK로 다시 잡지 않음 → 모터 지연·처짐으로 안 흘러감)
  - IK = 위치 3 + 숙임 1 (관절 4개). 숙임은 에피소드 시작 자세(VLA 종료 자세) 값으로 고정
  - 회전(wrist_roll)은 IK 없이 직접. 회전해도 끝단 위치 목표는 그대로라 IK가 위치를 유지
  - IK가 못 닿으면(1 cm 넘게 남음) 그 스텝의 이동은 무시
  - 작업 영역 상자(bounds) 밖으로 나가는 이동은 상자 경계에서 자름

액션 (모두 정책 출력과 같은 단위):
  dx, dy, dz  -1~1 → 스텝당 ±xyz_step m      (로봇 기준: x 앞, y 왼쪽, z 위)
  droll       -1~1 → 스텝당 ±roll_step 도
  gripper     0 닫기 / 1 유지 / 2 열기 (lerobot GamepadTeleop과 같은 값) → 스텝당 grip_step 단위
"""

from __future__ import annotations

import math

import numpy as np

from teleop_wrist import WristIK

ACTION_NAMES = ["delta_x", "delta_y", "delta_z", "delta_roll", "gripper"]
GRIPPER_CLOSE, GRIPPER_STAY, GRIPPER_OPEN = 0, 1, 2


class WristEEController:
    def __init__(self, urdf: str, frame: str, names: list[str], xyz_step: float = 0.008, roll_step: float = 6.0,
                 grip_step: float = 10.0, max_joint_step: float = 15.0, bounds: dict | None = None):
        self.names = list(names)  # 모터 순서: 팔 5 + gripper
        lo = np.full(len(names), -180.0)
        hi = np.full(len(names), 180.0)
        self.ik = WristIK(urdf, frame, self.names, lo, hi)
        for i, n in enumerate(self.names):
            try:
                jl = self.ik.kin.robot.get_joint_limits(n)
                lo[i], hi[i] = math.degrees(jl[0]) + 1, math.degrees(jl[1]) - 1
            except Exception:
                pass
        self.lo, self.hi = lo, hi
        self.xyz_step, self.roll_step, self.grip_step = xyz_step, roll_step, grip_step
        self.max_joint_step = max_joint_step
        self.bounds = bounds  # {"min": [x,y,z], "max": [x,y,z]} (m) 또는 None
        self.q_cmd = None
        self.blocked = ""

    def reset_from(self, q: np.ndarray) -> None:
        """현재 관절 각도(도)를 목표로 잡음. 숙임은 이 자세 값으로 고정."""
        self.q_cmd = np.array(q, dtype=float)
        self.p_cmd, self.pitch_cmd = self.ik.pose(self.q_cmd)
        self.blocked = ""

    def ee_pose(self) -> tuple[np.ndarray, float, float]:
        """(목표 끝단 위치 m, 숙임 도, 회전 도)"""
        return self.p_cmd.copy(), self.pitch_cmd, float(self.q_cmd[4])

    def step(self, action) -> np.ndarray:
        """액션 1개 → 새 관절 목표(도, 모터 순서). 로봇에 보내는 건 호출하는 쪽."""
        a = np.asarray(action, dtype=float)
        v = np.clip(a[:3], -1, 1)
        p_new = self.p_cmd + v * self.xyz_step
        if self.bounds is not None:
            p_new = np.clip(p_new, self.bounds["min"], self.bounds["max"])
        q = self.q_cmd
        roll_new = float(np.clip(q[4] + float(np.clip(a[3], -1, 1)) * self.roll_step, self.lo[4], self.hi[4]))
        if np.any(p_new != self.p_cmd) or roll_new != q[4]:
            # 회전만 해도 IK를 다시 풂: 끝단이 회전축에서 떨어져 있어서 회전하면 위치가 밀림 → 위치 목표 유지
            q_try = q.copy()
            q_try[4] = roll_new
            q_sol, perr, aerr = self.ik.solve(q_try, p_new, self.pitch_cmd)
            if perr < 0.01 and aerr < 5.0 and np.abs(q_sol[:4] - q[:4]).max() <= self.max_joint_step:
                q[:5], self.p_cmd, self.blocked = q_sol[:5], p_new, ""
            else:
                self.blocked = f"못 감 {perr * 100:.1f}cm/{aerr:.0f}°"
        g = int(round(a[4]))
        # 그리퍼 값: 0 = 끝까지 열림(약 115°), 100 = 닫힘 (11-22 재조립 후 손으로 닫고 열어서 확인)
        if g == GRIPPER_CLOSE:
            q[5] += self.grip_step
        elif g == GRIPPER_OPEN:
            q[5] -= self.grip_step
        q[5] = float(np.clip(q[5], 0.0, 100.0))
        return q.copy()
