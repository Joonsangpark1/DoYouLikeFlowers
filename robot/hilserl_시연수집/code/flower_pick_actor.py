"""HIL-SERL '잡고 뽑기' 하위 작업 actor (11-25). flower_actor.py(VLA 다음 전체 작업)를 대체.

11-25 연구 보고서(reports/SmolVLA HIL SERL 결합 설계.md)에서 찾은 문제를 반영:
  1) VLA 없음: 시작 자세 → (보정 있으면) 칸 측정 자세에서 손목 카메라 두 장으로 줄기 거리 측정 → 줄기 앞 PRE_M 지점까지 스크립트 접근
     → 거기서부터 정책. 보정 파일이 없으면 시연 도착 자세(stereo/slot_poses.json)에서 PRE_M 뒤로
  2) 짧은 지평: CONTROL_TIME_S 기본 12초 (= 120 스텝). γ 0.97 기준 60스텝 뒤 성공 가치 0.16 (예전 400스텝은 0)
  3) 성공 보상 자동 판정 + 1프레임 보상 후 바로 종료 (시연·온라인 규칙 통일):
       그리퍼를 닫으라고 명령했는데(명령 ≥ CLOSE_CMD) 줄기에 막혀 덜 닫힘(실측이 명령보다 STALL_DEG 이상 작음)
       + 끝단이 시작보다 LIFT_M 이상 올라감, 2스텝 연속. 사람 버튼도 유지: 1(꾹) 성공 / 2(꾹) 실패. 'VLA 잘못 감'은 없앰
  4) 관측 타이밍: 명령을 보내고 STEP_S(0.1초) 뒤에 관측 (시연 녹화와 같은 간격). 예전엔 명령 직후 바로 읽음
  5) 행동-결과 일치: 정책이 그리퍼를 시작 열림보다 더 열려고 해서 막히면 저장하는 행동을 '유지'로 바꿈
  6) 끝난 뒤 놓기·들어올리기는 다음 에피소드 시작 때 (예전엔 끝 관측 전에 움직여서 마지막 관측이 엉뚱했음)
학습기(서버)는 configs/flower_pick_train.json 으로 (오프라인 데이터 없이 시작, 개입이 시연 역할).

사용 (WSL, 송신기 켜 둔 상태):
  FLOWER_LAYOUT="sunflower,rose,blue" python flower_pick_actor.py      # 1·2·3번 칸 꽃
버튼: START 에피소드 · L1 꽃 바꾸기 · R1(누르고 있기) 개입 · L2/R2 그리퍼 · 1(꾹) 성공 · 2(꾹) 실패 · SELECT 종료
에피소드 사이: 사람이 뽑힌 꽃을 꽃병에 다시 꽂고 START
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import torch

# 11-26: 정책 CPU 추론 스레드 수 고정. 기본 8개는 카메라·통신 스레드와 부딪혀 한 번에 0.1~0.19 s (정책 5~10 fps),
# 따로 재면 4개 14 ms / 8개 17 ms / 16개 200 ms (i5-1240P) → 4개
torch.set_num_threads(int(os.environ.get("TORCH_THREADS", 4)))

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "stereo"))

import lerobot.rl.actor as A  # noqa: E402
from lerobot.rl.gym_manipulator import create_transition  # noqa: E402
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig  # noqa: E402
from lerobot.teleoperators.utils import TeleopEvents  # noqa: E402

import record_prior as RP  # noqa: E402  (패드·이동 도우미 재사용)
from lerobot_plugins import RemoteGamepad, RemoteGamepadConfig  # noqa: E402
from net_camera import NetCamera  # noqa: E402
from rl_obs import FRONT_KEY, STATE_KEY, WRIST_KEY, preprocess_front, preprocess_wrist  # noqa: E402
from usbip_camera import MjpegServer  # noqa: E402
from wrist_ee import GRIPPER_CLOSE, GRIPPER_OPEN, GRIPPER_STAY, WristEEController  # noqa: E402

E = os.environ.get
# 11-26 사용자: 강화학습은 뽑기만, 나머지(통으로 옮겨 놓기)는 위치 고정 IK → PULL_ONLY=1 (기본)
PULL_ONLY = E("PULL_ONLY", "1") == "1"
CONTROL_TIME_S = float(E("CONTROL_TIME_S", 20 if PULL_ONLY else 30))  # 뽑기만: 20 s (11-26 사용자: 12 → 늘림, 9 Hz면 약 180스텝)
PLACE_ABOVE_M = float(E("PLACE_ABOVE_M", 0.12))  # 통에 놓을 때 통 자세보다 이만큼 위에 먼저 도착 (11-26 사용자: 10 → 15 → 12 cm)
PLACE_DOWN_M = float(E("PLACE_DOWN_M", 0.10))    # 도착 뒤 z로 이만큼 내리고 그리퍼 엶 (11-26 사용자: 10 cm → 통 자세 +2 cm에서 놓음)
PLACE_RISE_M = float(E("PLACE_RISE_M", 0.03))    # 옮기는 중간 지점은 (지금 높이, 통 위 도착 높이) 중 높은 쪽보다 이만큼 더 위
BOX_XY = float(E("BOX_XY", 0.04))      # 뽑기 모드 작업 상자: 시작점 기준 앞뒤·좌우 ±4 cm
BOX_UP = float(E("BOX_UP", 0.12))      # 위로 12 cm (줄기 8.5 cm + 여유)
BOX_DOWN = float(E("BOX_DOWN", 0.03))  # 아래로 3 cm
PULL_SUCCESS_M = float(E("PULL_SUCCESS_M", 0.06))  # 1(성공)은 이만큼 이상 들어 올렸을 때만 받음 (잘못 누름 방지)
BIN_FILE = Path(__file__).resolve().parent / "configs/bin_pose.json"  # 통 위 관절 자세 (scripted_pick.py --record-bin)
STEP_S = float(E("STEP_S", 0.1))
MIN_OBS_DELAY = float(E("MIN_OBS_DELAY", 0.05))  # 명령 후 최소 이만큼 뒤에 관측
PICK_OPEN = float(E("PICK_OPEN", 69))      # 시작·접근 그리퍼 (0 끝까지 열림 ~ 100 닫힘). 11-25 사용자: 35° 열림 = 69. 정책은 이보다 더 못 엶
PRE_M = float(E("PRE_M", 0.03))            # 줄기 앞 몇 m에서 정책 시작
# 11-26 사용자: 그리퍼 선택지 닫기/유지 2개 + 손목 돌리기 고정 → 정책 행동 [dx, dy, dz, 그리퍼(0 닫기 1 유지)] (학습기 flower_pull2_train.json)
FIX_ROLL = E("FIX_ROLL", "1" if PULL_ONLY else "0") == "1"
GRIP2 = E("GRIP2", "1" if PULL_ONLY else "0") == "1"
EXTRA_IN_M = {2: 0.01, 3: 0.01}  # 11-26 사용자: YOLO 뒤 IK 접근 때 칸(배치) 2·3은 줄기 쪽으로 1 cm 더 (PRE_M에서 뺌)
CLOSE_CMD = float(E("CLOSE_CMD", 90))      # 이 이상 닫으라고 명령했으면 '닫는 중'
STALL_DEG = float(E("STALL_DEG", 8))       # 실측이 명령보다 이만큼 덜 닫혔으면 줄기에 막힌 것
LIFT_M = float(E("LIFT_M", 0.085))         # 줄기 꽂힌 깊이 8.5 cm
BIN_R = float(E("BIN_R", 0.06))            # 통 위로 판정하는 반경 (configs/bin_pose.json 끝단 위치 기준)
MIN_SUCCESS_S = float(E("MIN_SUCCESS_S", 1.0))
RB_HOLD_S = float(E("RB_HOLD_S", 0.3))
LOG_PATH = Path.home() / "lerobot_data" / E("FLOWER_HF_USER", "parkjoonsang") / "flower_pick_episodes.jsonl"
STEP_LOG = LOG_PATH.with_name("flower_pick_steps.csv")  # 11-25: 자동 판정 기준 맞추기용 (스텝마다 그리퍼 명령/실측, 들어 올린 높이, 개입)


def fixed_slot_point(fixed: dict, slot: int) -> tuple[np.ndarray, np.ndarray]:
    """고정 꽃병의 칸 줄기 점 (base 좌표 m)과 로봇→줄기 수평 방향. 호 중심이 베이스에서 arc_center_x 만큼 앞에 있을 수 있음"""
    th = np.radians(fixed["angles_deg"][str(slot)])
    R = fixed.get("arc_radius_m", fixed.get("radius_m")); cx = fixed.get("arc_center_x_m", 0.0)
    p = np.array([cx + R * np.cos(th), R * np.sin(th), fixed["grasp_z_m"]])
    u = np.array([np.cos(th), np.sin(th), 0.0])  # 접근 방향 = 호 중심(어깨 회전축)에서 줄기 쪽
    left = np.array([-u[1], u[0], 0.0])
    for corr in (fixed.get("tcp_correction_m", {}), fixed.get("slot_correction_m", {}).get(str(slot), {})):  # 전체 보정 + 칸별 보정 (칸 방향 기준: 앞 / 왼쪽 / 위)
        p = p + u * corr.get("forward", 0.0) + left * corr.get("left", 0.0) + np.array([0, 0, corr.get("up", 0.0)])
    return p, u


def fixed_slot_q(ik, fixed: dict, slot: int, q_seed: np.ndarray, pitch_deg: float, back_m: float = 0.0,
                 tol_m: float = 0.002) -> np.ndarray:
    """그리퍼 중심(TCP)이 줄기 점에서 back_m 만큼 로봇 쪽에 오도록 하는 관절값. TCP 오프셋 = stereo/stereo_config.json tcp_offset_m.
    11-25: 시연 숙임(−18°) 고정으로는 가까운 점(R 250 − 3 cm)에서 관절 범위에 걸려 5 mm 모자람 → 숙임을 시연값에서 가까운 순으로 바꿔 가며 tol 안에 닿는 첫 자세"""
    p, u = fixed_slot_point(fixed, slot)
    tcp = np.array(json.loads((HERE / "stereo/stereo_config.json").read_text()).get("tcp_offset_m", [0, 0, 0]), float)
    target = p - u * back_m
    best = None
    for dp in [0, -5, 5, -10, 10, -15, 15, -20, 20, -30, 30, -40, 40]:
        q = q_seed.copy()
        for _ in range(3):  # 프레임 목표 = TCP 목표 - R·tcp (자세가 바뀌므로 몇 번 반복)
            Rm = ik.fk(q)[:3, :3]
            q, perr, aerr = ik.solve(q, target - Rm @ tcp, pitch_deg + dp, iters=100)
        if best is None or perr < best[1]:
            best = (q, perr, dp)
        if perr <= tol_m:
            break
    q, perr, dp = best
    if perr > tol_m:
        raise RuntimeError(f"칸{slot} 고정 목표에 IK가 못 닿음 (최소 {perr * 1000:.1f} mm, 숙임 {pitch_deg + dp:.0f}°)")
    if dp:
        print(f"   칸{slot}: 숙임 {pitch_deg:.0f}° → {pitch_deg + dp:.0f}° 로 바꿔서 닿음 ({perr * 1000:.1f} mm)")
    return q


def learner_alive(_c=[0.0, True, 0]) -> bool:
    """학습기 50051 확인. 11-25: 1초 한 번 실패로 LEARNER OFF가 깜빡임 → 2초 기다리고 3번 연속 실패일 때만 꺼짐"""
    import socket
    if time.time() - _c[0] > 2.0:
        _c[0] = time.time()
        try:
            with socket.create_connection((E("LEARNER", "100.120.78.64"), 50051), timeout=2.0):
                _c[2] = 0
        except OSError:
            _c[2] += 1
        _c[1] = _c[2] < 3
    return _c[1]


class PickEnv:
    def __init__(self):
        raw = json.loads((HERE / "configs/flower_hil.json").read_text())
        rcfg, self.tcfg, ik = raw["env"]["robot"], raw["env"]["teleop"], raw["env"]["processor"]["inverse_kinematics"]
        self.layout = [s.strip() for s in E("FLOWER_LAYOUT", "sunflower,rose,blue").split(",")]
        self.pad = RemoteGamepad(RemoteGamepadConfig(port=self.tcfg["port"], deadzone=self.tcfg["deadzone"], always_intervene=True))
        self.pad.connect()
        self.wrist = NetCamera(port=5558); self.wrist.connect()
        # 11-25 사용자: C270도 정책 입력 (꽃병 + 통). 반드시 연결돼 있어야 함
        self.front = NetCamera(port=5559, wait_connect_s=60); self.front.connect()
        port = RP.by_id("/dev/serial/by-id/usb-1a86_*", rcfg["port"])
        self.robot = SO101Follower(SO101FollowerConfig(port=port, id=rcfg["id"], max_relative_target=10.0, disable_torque_on_disconnect=False))
        self.robot.connect()
        self.names = list(self.robot.bus.motors)
        self.ctrl = WristEEController(str(HERE / ik["urdf_path"]), ik["target_frame_name"], self.names,
                                      xyz_step=0.008, roll_step=6.0, grip_step=10.0, bounds=ik.get("end_effector_bounds"))
        self.start_pose = json.loads((RP.SMOLVLA_CODE / "start_pose_vla_trial4.json").read_text())
        self.start_pose["gripper"] = PICK_OPEN
        self.slot_poses = json.loads((HERE / "stereo/slot_poses.json").read_text())["slots"]
        ft = HERE / "configs/slot_targets.json"
        self.fixed = json.loads(ft.read_text()) if ft.exists() and E("FIXED_SLOTS", "1") == "1" else None
        self.calibrated = self.fixed is None and (HERE / "stereo/calib/hand_eye.json").exists() and (HERE / "stereo/calib/wrist_intrinsics.json").exists()
        self.rig = None
        from scripted_pick import ScriptedPicker
        self.picker = ScriptedPicker(self.robot, self.names)
        bp = HERE / "configs/bin_pose.json"
        self.bin_xy = None
        if bp.exists():
            b = json.loads(bp.read_text()); self.bin_xy = self.ctrl.ik.fk(np.array([b[n] for n in self.names]))[:2, 3]
        print(f"통 위치 {'없음 → 통에 넣기 자동 판정 안 됨 (scripted_pick.py --record-bin)' if self.bin_xy is None else np.round(self.bin_xy * 1000)}")
        self._slot_u = None
        if E("LOOK", "0") == "1" and E("LOOK_EACH", "1") != "1":  # 켤 때 한 번만 둘러보기 (에피소드마다 하면 생략)
            from observer_look import look_around
            self.picker.home()
            lay, _ = look_around(self.robot, self.names, self.wrist, save_dir=Path("/mnt/d/data/flower/look"))
            if all(lay.get(k) for k in "123"):
                self.layout = [lay["1"], lay["2"], lay["3"]]
            print(f"둘러보기 배치: {lay}")
        if self.calibrated:
            from common import Rig
            self.rig = Rig(robot=self.robot, cam=self.wrist)
        self.preview = MjpegServer(port=8080, fps=15)
        threading.Thread(target=self._preview_loop, daemon=True).start()
        print(f"미리보기 http://localhost:8080   배치 {self.layout}   거리 측정 {'사용' if self.calibrated else '없음(보정 전) → 시연 도착 자세 사용'}")
        self.analog_ok, self.ep, self.flower, self.holding = False, 0, None, False
        self.t0 = 0.0; self.z0 = 0.0; self.n_steps = self.n_interv = 0; self.ok_streak = 0

    def _preview_loop(self):
        while True:
            try:
                cams = [self.wrist] + ([self.front] if self.front is not None else [])
                img = np.hstack([cv2.cvtColor(c.read_latest(1000), cv2.COLOR_RGB2BGR) for c in cams])
                cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
                cv2.putText(img, RP._status[0], (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, RP._status[1], 2)
                self.preview.update_bgr(img)
            except Exception:
                pass
            time.sleep(1 / 15)

    def _q(self):
        return RP.read_q(self.robot, self.names)

    def _obs(self) -> dict:
        q = self._q().astype(np.float32)
        img = preprocess_wrist(self.wrist.read_fresh())
        fimg = preprocess_front(self.front.read_fresh())
        return {WRIST_KEY: torch.from_numpy(img).permute(2, 0, 1).float().unsqueeze(0) / 255.0,
                FRONT_KEY: torch.from_numpy(fimg).permute(2, 0, 1).float().unsqueeze(0) / 255.0,
                STATE_KEY: torch.from_numpy(q).unsqueeze(0)}

    def _ee_z(self, q) -> float:
        return float(self.ctrl.ik.fk(q)[2, 3])

    # ---------- 접근 (스크립트) ----------
    def _approach(self, slot: int) -> np.ndarray:
        P = self.slot_poses[str(slot)]
        ik = self.ctrl.ik
        if self.fixed is not None:  # 11-25 꽃병 위치 고정: slot_check로 확인한 직선 궤적 그대로 (어깨만 돌리기 → 8 cm 앞 → 줄기 PRE_M 앞)
            back = PRE_M - EXTRA_IN_M.get(slot, 0.0)
            self._slot_u = self.picker.approach(slot, back_m=back, step_cb=lambda m: RP.set_status(f"APPROACH {m}", RP.YELLOW), grip=PICK_OPEN)
            return self._q()
        if self.rig is not None:
            from stereo_measure import measure_slot
            r = measure_slot(self.rig, slot)
            print(f"   측정: {'OK' if r['ok'] else '실패'} {r.get('vs_demo_arrive_mm')} mm")
            if r["ok"]:
                X = np.array(r["stem_xyz_m"])
                T = ik.fk(self._q()); a = T[:3, :3] @ ik.a_local
                q, err = self.rig.move_ee(X - a * PRE_M, duration_s=2.0)
                return q
        # 보정 전 또는 측정 실패: 시연 도착 자세에서 PRE_M 뒤
        q_arr = np.array(P["arrive_q"]); q_arr[5] = PICK_OPEN
        T = ik.fk(q_arr); a = T[:3, :3] @ ik.a_local
        q_pre, perr, _ = ik.solve(q_arr.copy(), T[:3, 3] - a * PRE_M, P["pitch_deg"], iters=60)
        q_pre[5] = PICK_OPEN
        RP.move_smooth(self.robot, dict(zip(self.names, np.array(P["look_q"])[:5].tolist() + [PICK_OPEN])))
        RP.move_smooth(self.robot, dict(zip(self.names, q_pre.tolist())))
        return self._q()

    # ---------- 뽑은 뒤 통에 넣기 (스크립트, 11-26 뽑기만 모드) ----------
    def _place_scripted(self):
        """scripted_pick.pick_place의 뽑은 뒤 부분과 같음: 칸 반대 방향으로 5 cm 빠지기 → 어깨만 통 쪽 → 통 위 자세 → 그리퍼 열기."""
        try:
            RP.set_status("PLACE (scripted IK)", RP.YELLOW)
            g = float(self._q()[5])
            if self._slot_u is not None:
                _, u, pitch = self._slot_u
                q = self._q(); p, _ = self.ctrl.ik.pose(q)
                self.picker.line_to(p - u * 0.05, pitch)
            if BIN_FILE.exists():
                # 11-26 사용자: 통 자세보다 z로 PLACE_ABOVE_M(10 cm) 위에 먼저 도착 → z 방향으로 똑바로 내려가서 놓기 → 다시 올라오기
                b = json.loads(BIN_FILE.read_text()); qb = np.array([b[n] for n in self.names])
                tcp = np.array(json.loads((HERE / "stereo/stereo_config.json").read_text()).get("tcp_offset_m", [0, 0, 0]), float)
                Tb = self.ctrl.ik.fk(qb)
                p_bin = Tb[:3, 3] + Tb[:3, :3] @ tcp           # 통 위 놓는 점 (그리퍼 중심)
                pitch_b = self.ctrl.ik.pose(qb)[1]
                up = np.array([0.0, 0.0, PLACE_ABOVE_M])
                # 11-26 사용자: 옮기는 궤적은 z로 올라가면서 이동 (어깨만 먼저 돌리면 꽃이 지금 높이로 휩쓸림)
                # 지금 위치 → (통 쪽 중간 지점, 이동 높이)까지 올라가며 → 통 위 10 cm
                q = self._q(); p_now, pitch_now = self.ctrl.ik.pose(q)
                T = self.ctrl.ik.fk(q); p_now = T[:3, 3] + T[:3, :3] @ tcp
                z_travel = max(p_now[2], (p_bin + up)[2]) + PLACE_RISE_M
                mid = p_now + (p_bin + up - p_now) * 0.5
                RP.set_status("PLACE: rise while moving", RP.YELLOW)
                self.picker.line_to(np.array([mid[0], mid[1], z_travel]), (pitch_now + pitch_b) / 2)
                RP.set_status("PLACE: above bin", RP.YELLOW)
                self.picker.line_to(p_bin + up, pitch_b)        # 통 위 10 cm 도착
                RP.set_status("PLACE: down", RP.YELLOW)
                self.picker.line_to(p_bin + up - np.array([0.0, 0.0, PLACE_DOWN_M]), pitch_b)  # z로 10 cm 똑바로 내리기
                self.picker.grip(PICK_OPEN)                     # 놓기
                RP.set_status("PLACE: up", RP.YELLOW)
                self.picker.line_to(p_bin + up, pitch_b)        # 다시 올라오기 (꽃 안 건드리게)
                print(f"   [넣기] 통 위 {PLACE_ABOVE_M * 100:.0f} cm 도착 → {PLACE_DOWN_M * 100:.0f} cm 내려서 놓음")
            else:
                print("   [넣기] 통 위치(configs/bin_pose.json) 없음 → 놓지 않음 (scripted_pick.py --record-bin)")
            self._slot_u = None  # 다음 시작 때 칸 방향으로 빠지기 생략 (이미 통 쪽)
            self.holding = False
        except Exception as e:
            print("   [넣기] 실패:", e)
            self.holding = True  # 다음 시작 때 그리퍼 열어 놓기

    # ---------- 에피소드 시작 ----------
    def reset_transition(self):
        if self.holding:  # 지난 에피소드에서 잡고 있던 꽃 놓기 (사람이 받거나 통 위에서)
            RP.set_status("RELEASE", RP.YELLOW)
            for g in [[0, 0, 0, 0, GRIPPER_OPEN]] * 6:
                self.robot.bus.sync_write("Goal_Position", dict(zip(self.names, self.ctrl.step(np.array(g, np.float32)), strict=True)))
                time.sleep(0.1)
            self.holding = False
        RP.set_status("MOVING TO START", RP.YELLOW)
        if self._slot_u is not None:  # 칸 방향 반대로 8 cm 빠진 뒤 시작 자세 (옆 꽃·꽃병 안 치게)
            try:
                p_stem, u, pitch = self._slot_u
                q = self._q(); p, _ = self.ctrl.ik.pose(q)
                self.picker.line_to(np.array([p[0], p[1], max(p[2], p_stem[2])]) - u * 0.08, pitch)
            except Exception as e:
                print("   빠지기 실패, 바로 시작 자세로:", e)
        self.picker.grip(PICK_OPEN)
        self.picker.home()
        flower = self.flower or self.layout[self.ep % 3]
        volt = RP.read_volt(self.robot)
        print(f"\n[대기] pick ep{self.ep}  꽃 {flower}(칸{self.layout.index(flower) + 1})  {volt}V  → 꽃을 꽃병에 꽂고 START")
        self.pad.clear_pressed()
        while True:
            st = self.pad._live_state() or {}
            if not self.analog_ok and max(abs(float(st.get("rx", 0))), abs(float(st.get("ry", 0)))) > 0.5:
                self.analog_ok = True
            if self.pad.pop_pressed("back"):
                raise KeyboardInterrupt
            if self.pad.pop_pressed("lb"):
                flower = self.layout[(self.layout.index(flower) + 1) % 3]; print(f"   꽃 -> {flower}")
            if not self.analog_ok:
                RP.set_status(f"ANALOG? move RIGHT stick  [{flower}]", RP.YELLOW); self.pad.pop_pressed("start")
            elif E("NO_LEARNER", "0") != "1" and not learner_alive():
                RP.set_status("LEARNER OFF", RP.RED); self.pad.pop_pressed("start")
            else:
                RP.set_status(f"PICK READY ep{self.ep} [{flower}] {volt}V  START=go L1=flower", RP.WHITE)
                if self.pad.pop_pressed("start"):
                    break
            time.sleep(0.05)
        self.flower = flower
        if E("LOOK_EACH", "1") == "1":  # 11-25 사용자: 에피소드마다 시작 전에 둘러보기(YOLO)로 배치 확인
            from observer_look import look_around
            RP.set_status("LOOK AROUND (YOLO)", RP.YELLOW)
            lay, _ = look_around(self.robot, self.names, self.wrist, save_dir=Path("/mnt/d/data/flower/look"))
            if all(lay.get(k) for k in "123"):
                self.layout = [lay["1"], lay["2"], lay["3"]]
                print(f"   배치(YOLO): {'-'.join(f[0].upper() for f in self.layout)}  각도 {lay.get('_psi_deg')}")
            else:
                print(f"   배치 판단 실패 {lay} → 이전 배치 사용 {self.layout}")
        RP.set_status(f"APPROACH slot {self.layout.index(flower) + 1}", RP.YELLOW)
        q0 = self._approach(self.layout.index(flower) + 1)
        q0 = RP.hold_here(self.robot)
        self.ctrl.reset_from(q0)
        self.z0 = self._ee_z(q0)
        if PULL_ONLY:  # 정책이 움직일 수 있는 범위를 줄기 주변 상자로 (원래는 꽃병~통 전체 32x43x30 cm)
            p0 = self.ctrl.p_cmd
            self.ctrl.bounds = {"min": [p0[0] - BOX_XY, p0[1] - BOX_XY, p0[2] - BOX_DOWN],
                                "max": [p0[0] + BOX_XY, p0[1] + BOX_XY, p0[2] + BOX_UP]}
        self.pad.clear_pressed()
        self.t0 = time.perf_counter(); self.n_steps = self.n_interv = 0; self.ok_streak = 0; self.picked = False
        print("[정책] 잡고 뽑기" + (f" ({CONTROL_TIME_S:.0f} s, 뽑으면 1 꾹 → 통에 넣기는 자동)" if PULL_ONLY else "") + ". R1 개입 / 1 꾹 성공 / 2 꾹 실패")
        obs0 = self._obs()
        self.t_last_obs = time.perf_counter()
        return create_transition(observation=obs0, info={}, complementary_data={})

    # ---------- 한 스텝 ----------
    def step_transition(self, action: torch.Tensor):
        t_step = time.perf_counter()
        a = action.detach().reshape(-1).cpu().numpy().astype(np.float32)
        st = self.pad._live_state() or {}
        if int(st.get("btn", 0)) & RP.BUTTONS["rb"]:
            self.last_rb_t = time.perf_counter()
        intervene = E("ALWAYS_TELEOP", "0") == "1" or time.perf_counter() - getattr(self, "last_rb_t", -1e9) < RB_HOLD_S
        if intervene:
            a = RP.pad_action(self.pad, self.tcfg); self.n_interv += 1
        elif FIX_ROLL:  # 정책 출력 [dx, dy, dz, 그리퍼] → 컨트롤러용 [dx, dy, dz, droll=0, 그리퍼]
            a = np.concatenate([np.clip(a[:3], -1, 1), [0.0], [float(np.clip(np.rint(a[3]), 0, 2)) if a.shape[0] > 3 else GRIPPER_STAY]])
        else:
            a = np.concatenate([np.clip(a[:4], -1, 1), [float(np.clip(np.rint(a[4]), 0, 2)) if a.shape[0] > 4 else GRIPPER_STAY]])
        a = np.asarray(a, np.float32).copy()
        if FIX_ROLL:
            a[3] = 0.0  # 사람 패드도 손목 돌리기 안 함
        if GRIP2 and int(a[4]) == GRIPPER_OPEN:
            a[4] = GRIPPER_STAY  # 열기 없음 (사람·정책 둘 다). 시작은 69로 열려 있고 놓기는 IK가 함
        q = self.ctrl.step(a)
        if q[5] < PICK_OPEN:  # 시작 열림보다 더 못 엶 → 실제로 안 움직였으니 저장 행동도 '유지'
            q[5] = self.ctrl.q_cmd[5] = PICK_OPEN
            if int(a[4]) == GRIPPER_OPEN:
                a[4] = GRIPPER_STAY
        self.robot.bus.sync_write("Goal_Position", dict(zip(self.names, q, strict=True)))
        self.n_steps += 1
        # 11-26: 관측 간격을 '이전 관측부터 STEP_S'로 맞춤 (전에는 '명령부터 STEP_S'라 정책 추론 시간이 매 스텝 더해져 실제 5.6 Hz).
        # 명령 후 최소 MIN_OBS_DELAY는 기다려서 모터가 움직인 뒤 관측
        t_next = max(getattr(self, "t_last_obs", t_step) + STEP_S, time.perf_counter() + MIN_OBS_DELAY)
        time.sleep(max(0.0, t_next - time.perf_counter()))
        obs = self._obs()
        self.t_last_obs = time.perf_counter()
        qm = obs[STATE_KEY][0].numpy()
        el = time.perf_counter() - self.t0
        stalled = self.ctrl.q_cmd[5] >= CLOSE_CMD and qm[5] < self.ctrl.q_cmd[5] - STALL_DEG and qm[5] > PICK_OPEN + 5
        lifted = self._ee_z(qm) - self.z0 >= LIFT_M
        self.ok_streak = self.ok_streak + 1 if (stalled and lifted) else 0
        if self.ok_streak >= 2 and not self.picked:
            self.picked = True; print(f"   [1단계] 잡고 뽑음 {el:.1f}s")
        # 11-25 한 에피소드 = 잡기 + 통에 넣기: 뽑은 뒤 통 위(BIN_R 안)에서 그리퍼가 열리면 성공
        ee = self.ctrl.ik.fk(qm)[:3, 3]
        over_bin = self.bin_xy is not None and np.linalg.norm(ee[:2] - self.bin_xy) < BIN_R
        released = qm[5] <= PICK_OPEN + 4
        auto_ok = (not PULL_ONLY) and self.picked and over_bin and released and el >= MIN_SUCCESS_S
        new = not STEP_LOG.exists()
        with STEP_LOG.open("a") as f:
            if new:
                f.write("time,ep,step,intervene,grip_action,grip_cmd,grip_meas,lift_cm,ee_x,ee_y,ee_z,picked,over_bin\n")
            f.write(f"{time.strftime('%H:%M:%S')},{self.ep},{self.n_steps},{int(intervene)},{int(a[4])},{self.ctrl.q_cmd[5]:.1f},{qm[5]:.1f},"
                    f"{(self._ee_z(qm) - self.z0) * 100:.1f},{ee[0]:.3f},{ee[1]:.3f},{ee[2]:.3f},{int(self.picked)},{int(over_bin)}\n")
        lift_now = self._ee_z(qm) - self.z0
        success = auto_ok or (RP.held(self.pad, "y") and el >= MIN_SUCCESS_S and (not PULL_ONLY or lift_now >= PULL_SUCCESS_M))
        failure = not success and RP.held(self.pad, "b")  # 11-25 사용자: 실패 = 2(꾹) (예전 3)
        truncated = el >= CONTROL_TIME_S
        done = success or failure
        RP.set_status(f"PICK ep{self.ep} [{self.flower}] {el:4.1f}/{CONTROL_TIME_S:.0f}s {'INTERVENE ' if intervene else ''}"
                      f"{'PICKED ' if self.picked else ''}grip {qm[5]:.0f}/{self.ctrl.q_cmd[5]:.0f} lift {(self._ee_z(qm) - self.z0) * 100:.1f}cm", RP.RED if intervene else RP.GREEN)
        if done or truncated:
            result = ("success(auto)" if auto_ok else "success") if success else "failure" if failure else "timeout"
            rec = {"ep": self.ep, "flower": self.flower, "result": result, "picked": self.picked, "steps": self.n_steps, "intervention_steps": self.n_interv,
                   "seconds": round(el, 1), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"   [끝] {result}  {self.n_steps}스텝 (개입 {self.n_interv})  {el:.1f}s")
            self.holding = qm[5] > PICK_OPEN + 5 and not success
            if PULL_ONLY and success:
                self._place_scripted()  # 뽑은 뒤 통까지 위치 고정 IK로 옮겨 놓기
            self.ep += 1
            if success:
                self.flower = None  # 다음 꽃으로
        a_store = np.array([a[0], a[1], a[2], a[4]], np.float32) if FIX_ROLL else a  # 학습 데이터에는 손목 돌리기 칸 빼고 저장
        return create_transition(
            observation=obs, action=torch.from_numpy(a_store).unsqueeze(0), reward=1.0 if success else 0.0,
            done=bool(done), truncated=bool(truncated and not done),
            info={TeleopEvents.IS_INTERVENTION: intervene},
            complementary_data={"teleop_action": torch.from_numpy(a_store).unsqueeze(0), "discrete_penalty": 0.0},
        )


def _make_env(cfg):
    return PickEnv(), None


A.make_robot_env = _make_env
A.make_processors = lambda env, teleop, cfg, device: (None, None)
A.reset_and_build_transition = lambda env, ep, ap: env.reset_transition()
A.step_env_and_process_transition = lambda env, transition, action, env_processor, action_processor: env.step_transition(action)

if __name__ == "__main__":
    out = Path.home() / "lerobot_data" / E("FLOWER_HF_USER", "parkjoonsang") / "flower_pick_actor" / time.strftime("%m%d_%H%M%S")
    sys.argv = [sys.argv[0], "--config_path", str(HERE / ("configs/flower_pull2_train.json" if FIX_ROLL else "configs/flower_pick_train.json")),
                f"--output_dir={out}", "--policy.device=cpu", "--policy.storage_device=cpu",
                f"--policy.actor_learner_config.learner_host={E('LEARNER', '100.120.78.64')}"]
    try:
        A.actor_cli()
    except KeyboardInterrupt:
        print("종료"); os._exit(0)
    print("실행기가 에러로 멈춤"); os._exit(2)
