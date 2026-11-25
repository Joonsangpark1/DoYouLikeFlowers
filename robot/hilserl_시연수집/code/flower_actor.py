"""HIL-SERL 실물 actor (11-23). LeRobot 공식 actor(lerobot.rl.actor)의 통신·정책 부분은 그대로 쓰고,
환경(로봇) 부분만 우리 방식으로 바꿔 끼운다.

우리 방식 (공식과 다른 점):
  - 행동 5차원: [dx, dy, dz, droll] 연속 + 그리퍼 이산(0 닫기/1 유지/2 열기)  → wrist_ee.WristEEController
  - 정책 입력: 손목 카메라 128x128 + 관절 6 (rl_obs.py, 시연 변환과 같은 함수)
  - 에피소드 시작: 시작 자세(그리퍼 먼저 35°) → 사람이 START → VLA가 꽃 앞까지 → 강화학습 정책이 이어받음
  - 성공 판정: **사람이 1을 0.4초 꾹** (사용자 결정 11-23, 보상 분류기 없이). 3 = 실패, 시간 초과 = 잘림
  - 개입: **R1을 누르고 있는 동안** 게임패드 조종이 정책 대신 들어감 (그 구간은 개입으로 학습에 표시)

학습기(서버 sior)를 먼저 켠다:  bash ~/lerobot_flower/rl/start_learner.sh
그다음 노트북 WSL (녹화 송신기 3개 켜 둔 상태):
  python flower_actor.py                      # 기본: 학습기 100.120.78.64:50051
  LEARNER=1.2.3.4 python flower_actor.py
버튼 (일반 패드): START 에피소드 시작 · L1 꽃 바꾸기 · R1(누르고 있기) 개입 · L2/R2 그리퍼 ·
                 1(꾹) 성공 · 3(꾹) 실패 · 2(꾹) VLA 잘못 감 → 되돌아가 다시 · SELECT 종료
미리보기: http://localhost:8080
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lerobot.rl.actor as A  # noqa: E402
from lerobot.processor import TransitionKey  # noqa: E402
from lerobot.rl.gym_manipulator import create_transition  # noqa: E402
from lerobot.teleoperators.utils import TeleopEvents  # noqa: E402

import record_prior as RP  # noqa: E402  (Vla, 패드·이동 도우미 재사용)
from lerobot_plugins import RemoteGamepad, RemoteGamepadConfig  # noqa: E402
from net_camera import NetCamera  # noqa: E402
from rl_obs import STATE_KEY, WRIST_KEY, preprocess_wrist  # noqa: E402
from usbip_camera import MjpegServer  # noqa: E402
from wrist_ee import GRIPPER_STAY, WristEEController  # noqa: E402

CONTROL_TIME_S = float(os.environ.get("CONTROL_TIME_S", 60))
GRIP_MIN = float(os.environ.get("GRIP_MIN", 69))  # 정책이 열 수 있는 한계 (그리퍼 0 열림~100 닫힘, 69 ≈ 35° 열림). 개입(R1)은 제한 없음
LOG_PATH = Path.home() / "lerobot_data" / os.environ.get("FLOWER_HF_USER", "parkjoonsang") / "flower_rl_episodes.jsonl"
STEP_LOG = Path.home() / "lerobot_data" / os.environ.get("FLOWER_HF_USER", "parkjoonsang") / "flower_rl_steps.csv"  # time,ep,rb_raw,intervene,grip_action,policy_grip,grip_target
RB_HOLD_S = float(os.environ.get("RB_HOLD_S", 0.3))  # R1을 뗀 뒤 이 시간까지는 개입으로 봄
MIN_SUCCESS_S = float(os.environ.get("MIN_SUCCESS_S", 3.0))  # 정책 시작 후 이 시간 안의 성공(1)은 무시


_learner_check = [0.0, True]


def learner_alive(every_s: float = 2.0) -> bool:
    """학습기 gRPC 포트가 열려 있는지 (2초마다 한 번만 확인)."""
    import socket
    if time.time() - _learner_check[0] > every_s:
        _learner_check[0] = time.time()
        try:
            with socket.create_connection((os.environ.get("LEARNER", "100.120.78.64"), 50051), timeout=1.0):
                _learner_check[1] = True
        except OSError:
            _learner_check[1] = False
    return _learner_check[1]


class VlaArgs:  # record_prior.Vla가 쓰는 설정값 (record_prior 기본값과 같게)
    def __init__(self):
        self.robot_port = RP.by_id("/dev/serial/by-id/usb-1a86_*", "/dev/ttyACM0")
        self.max_step_deg, self.server, self.model, self.fps = 10.0, os.environ.get("FLOWER_SERVER", "100.120.78.64:8080"), RP.DEFAULT_MODEL, 10
        self.vla_gripper, self.vla_gripper_state = 69.0, 15.9
        self.vla_min_s, self.vla_max_s, self.settle_s, self.settle_deg = 2.0, 15.0, 1.0, 0.5


class FlowerEnv:
    def __init__(self):
        raw = json.loads((HERE / "configs/flower_hil.json").read_text())
        self.tcfg, ik = raw["env"]["teleop"], raw["env"]["processor"]["inverse_kinematics"]
        self.args = VlaArgs()
        self.pad = RemoteGamepad(RemoteGamepadConfig(port=self.tcfg["port"], deadzone=self.tcfg["deadzone"], always_intervene=True))
        self.pad.connect()
        # C270은 강화학습에 안 씀 (정책 입력 아님, 성공은 사람이 판정). FRONT=0이면 연결 안 함 (11-24: 독이 불안정해 C270 뺌)
        self.front = None
        if os.environ.get("FRONT", "1") != "0":
            self.front = NetCamera(port=5559)
            self.front.connect()
        self.wrist = NetCamera(port=5558)
        self.vla = RP.Vla(self.args, self.wrist)  # 로봇 + 손목 카메라 연결
        self.robot, self.names = self.vla.robot, self.vla.names
        self.ctrl = WristEEController(str(HERE / ik["urdf_path"]), ik["target_frame_name"], self.names,
                                      xyz_step=0.008, roll_step=6.0, grip_step=10.0, bounds=ik.get("end_effector_bounds"))
        self.start_pose = json.loads((RP.SMOLVLA_CODE / "start_pose_vla_trial4.json").read_text())
        self.start_pose["gripper"] = self.args.vla_gripper
        self.preview = MjpegServer(port=8080, fps=15)
        threading.Thread(target=self._preview_loop, daemon=True).start()
        print("미리보기: http://localhost:8080  (왼쪽 손목 / 오른쪽 고정)")
        if not self.vla.load():
            raise ConnectionError("VLA 서버 연결 실패 (sior start_server.sh)")
        self.analog_ok, self.flower, self.retry_flower = False, None, None
        self.ep = 0
        self.t0 = 0.0
        self.n_steps = self.n_interv = 0

    # ---------- 화면 ----------
    def _preview_loop(self):
        while True:
            try:
                cams = [self.wrist] + ([self.front] if self.front is not None else [])
                img = np.hstack([cv2.cvtColor(c.read_latest(1000), cv2.COLOR_RGB2BGR) for c in cams])
                cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
                cv2.putText(img, RP._status[0], (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, RP._status[1], 2)
                self.preview.update_bgr(img)
            except Exception:
                pass
            time.sleep(1 / 15)

    # ---------- 관측 ----------
    def _obs(self) -> dict:
        q = RP.read_q(self.robot, self.names).astype(np.float32)
        img = preprocess_wrist(self.wrist.read_latest())
        return {
            WRIST_KEY: torch.from_numpy(img).permute(2, 0, 1).float().unsqueeze(0) / 255.0,
            STATE_KEY: torch.from_numpy(q).unsqueeze(0),
        }

    # ---------- 에피소드 시작 ----------
    def reset_transition(self):
        while True:
            RP.set_status("MOVING TO START", RP.YELLOW)
            RP.move_smooth(self.robot, self.start_pose, gripper_first=True)
            # 꽃은 에피소드마다 돌아가며 (11-23: 처음 고른 꽃만 계속 나오던 문제). 되돌아온 경우만 같은 꽃
            flower = self.retry_flower or RP.FLOWERS[self.ep % 3]
            self.retry_flower = None
            volt = RP.read_volt(self.robot)
            print(f"\n[대기] 강화학습 ep{self.ep}  꽃 {flower}  배터리 {volt}V  → 꽃을 꽃병에 다시 꽂고 START (L1 꽃 바꾸기, SELECT 종료)")
            self.pad.clear_pressed()
            while True:
                st = self.pad._live_state() or {}
                if not self.analog_ok and max(abs(float(st.get("rx", 0))), abs(float(st.get("ry", 0)))) > 0.5:
                    self.analog_ok = True
                    print("   ANALOG 확인됨")
                if self.pad.pop_pressed("back"):
                    raise KeyboardInterrupt
                if self.pad.pop_pressed("lb"):
                    flower = RP.FLOWERS[(RP.FLOWERS.index(flower) + 1) % 3]
                    print(f"   꽃 -> {flower}")
                if not self.analog_ok:
                    RP.set_status(f"ANALOG? move RIGHT stick  RL ep{self.ep} [{flower}] {volt}V", RP.YELLOW)
                    self.pad.pop_pressed("start")
                elif not learner_alive():
                    # 11-24: 학습기가 꺼진 채 에피소드 5개(성공 4)를 돌려 경험이 버려짐 → 학습기 꺼져 있으면 시작 막기
                    RP.set_status(f"LEARNER OFF - start learner on server  RL ep{self.ep} [{flower}]", RP.RED)
                    if self.pad.pop_pressed("start"):
                        print("   학습기(서버 50051)가 꺼져 있어서 시작 안 함. 서버에서 학습기를 켜 주세요")
                else:
                    RP.set_status(f"RL READY ep{self.ep} [{flower}] {volt}V  START=go L1=flower SELECT=quit", RP.WHITE)
                    if self.pad.pop_pressed("start"):
                        break
                time.sleep(0.05)
            self.flower = flower
            # 그리퍼 먼저 닫고 VLA
            RP.move_smooth(self.robot, {**dict(zip(self.names, RP.read_q(self.robot, self.names))), "gripper": self.args.vla_gripper})
            time.sleep(0.3)
            print(f"[VLA] {RP.TASKS[flower]}")
            reason, vla_s = self.vla.run(RP.TASKS[flower], self.args, self.pad)
            q0 = RP.hold_here(self.robot)
            print(f"   VLA 끝: {reason}, {vla_s:.1f}s")
            if reason in ("abort", "pad_lost", "error"):
                RP.set_status("REWIND (VLA path reversed)", RP.YELLOW)
                RP.rewind(self.robot, self.names, self.vla.history, q0, self.args.vla_gripper, self.args.fps)
                self.retry_flower = flower
                continue
            break
        self.ctrl.reset_from(q0)
        self.pad.clear_pressed()
        self.t0 = time.perf_counter()
        self.n_steps = self.n_interv = 0
        print("[강화학습] 정책 실행. R1 누르고 있으면 개입 / 1 꾹 성공 / 3 꾹 실패 / 2 꾹 VLA 잘못 감")
        return create_transition(observation=self._obs(), info={}, complementary_data={})

    # ---------- 한 스텝 ----------
    def step_transition(self, action: torch.Tensor):
        a = action.detach().reshape(-1).cpu().numpy().astype(np.float32)
        st = self.pad._live_state() or {}
        rb_now = bool(int(st.get("btn", 0)) & RP.BUTTONS["rb"])
        if rb_now:
            self.last_rb_t = time.perf_counter()
        # R1 신호가 잠깐 끊겨도 0.3초까지는 개입으로 봄 (11-24: R1 누르고 있는데 그리퍼가 열린다는 보고 → 한 스텝씩 정책이 끼어드는 것 의심)
        intervene = rb_now or (time.perf_counter() - getattr(self, "last_rb_t", -1e9) < RB_HOLD_S)
        policy_a = a.copy()
        if intervene:
            a = RP.pad_action(self.pad, self.tcfg)
            self.n_interv += 1
        else:
            a = np.concatenate([np.clip(a[:4], -1, 1), [float(np.clip(np.rint(a[4]), 0, 2)) if a.shape[0] > 4 else GRIPPER_STAY]])
        q = self.ctrl.step(a)
        if not intervene and q[5] < GRIP_MIN:  # 정책은 35°(69)보다 더 벌리지 못함 (11-23: 무작위 초기 정책이 그리퍼를 끝까지 열어버림)
            q[5] = self.ctrl.q_cmd[5] = GRIP_MIN
        self.robot.bus.sync_write("Goal_Position", dict(zip(self.names, q, strict=True)))
        self.n_steps += 1
        # 스텝 기록 (그리퍼가 왜 열렸는지 등 확인용): 시각, 에피소드, R1 원신호, 개입 판정, 실행 그리퍼 행동, 정책 그리퍼 출력, 그리퍼 목표
        with STEP_LOG.open("a") as f:
            f.write(f"{time.strftime('%H:%M:%S')},{self.ep},{int(rb_now)},{int(intervene)},{a[4]:.0f},"
                    f"{policy_a[4] if policy_a.shape[0] > 4 else -1:.2f},{q[5]:.1f}\n")

        el = time.perf_counter() - self.t0
        # 정책 시작 직후 MIN_SUCCESS_S 안의 1번은 무시 (11-24: 1~2초 만의 '성공' 3개가 잘못 저장됨 — ANALOG 꺼진 오른쪽 스틱/잔여 입력 의심)
        success = RP.held(self.pad, "y") and el >= MIN_SUCCESS_S
        failure = not success and RP.held(self.pad, "a")
        vla_wrong = not success and not failure and RP.held(self.pad, "b")
        truncated = el >= CONTROL_TIME_S
        done = success or failure or vla_wrong
        RP.set_status(f"RL ep{self.ep} [{self.flower}] {el:4.1f}/{CONTROL_TIME_S:.0f}s  {'INTERVENE ' if intervene else ''}"
                      f"hold 1=ok 3=fail 2=vla  {self.ctrl.blocked}", RP.RED if intervene else RP.GREEN)
        if done or truncated:
            result = "success" if success else "failure" if failure else "vla_wrong" if vla_wrong else "timeout"
            rec = {"ep": self.ep, "flower": self.flower, "result": result, "steps": self.n_steps, "intervention_steps": self.n_interv,
                   "seconds": round(el, 1), "time": time.strftime("%Y-%m-%d %H:%M:%S")}
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"   [끝] {result}  {self.n_steps}스텝 (개입 {self.n_interv})  {el:.0f}s")
            # 꽃 놓고 올리기
            for g in [[0, 0, 0, 0, 2]] * 6 + [[0, 0, 0.8, 0, GRIPPER_STAY]] * 8:
                self.robot.bus.sync_write("Goal_Position", dict(zip(self.names, self.ctrl.step(np.array(g, np.float32)), strict=True)))
                time.sleep(0.1)
            self.ep += 1
            if vla_wrong:
                self.retry_flower = self.flower
        return create_transition(
            observation=self._obs(), action=torch.from_numpy(a).unsqueeze(0), reward=1.0 if success else 0.0,
            done=bool(done), truncated=bool(truncated and not done),
            info={TeleopEvents.IS_INTERVENTION: intervene},
            complementary_data={"teleop_action": torch.from_numpy(a).unsqueeze(0), "discrete_penalty": 0.0},
        )


_env: FlowerEnv | None = None


def _make_env(cfg):
    global _env
    _env = FlowerEnv()
    return _env, None


A.make_robot_env = _make_env
A.make_processors = lambda env, teleop, cfg, device: (None, None)
A.reset_and_build_transition = lambda env, ep, ap: env.reset_transition()
A.step_env_and_process_transition = lambda env, transition, action, env_processor, action_processor: env.step_transition(action)

if __name__ == "__main__":
    out = Path.home() / "lerobot_data" / os.environ.get("FLOWER_HF_USER", "parkjoonsang") / "flower_rl_actor" / time.strftime("%m%d_%H%M%S")
    sys.argv = [sys.argv[0], "--config_path", str(HERE / "configs/flower_rl_train.json"),
                f"--output_dir={out}", "--policy.device=cpu", "--policy.storage_device=cpu",
                f"--policy.actor_learner_config.learner_host={os.environ.get('LEARNER', '100.120.78.64')}"]
    try:
        A.actor_cli()
    except KeyboardInterrupt:  # SELECT 또는 Ctrl+C = 정상 종료
        print("종료 (SELECT/Ctrl+C)")
        os._exit(0)
    # actor_cli가 안에서 에러를 잡고 그냥 돌아온 경우 (독 끊김 등) → flower_actor_loop.sh가 다시 켜도록 0이 아닌 값
    print("실행기가 에러로 멈춤 → 다시 시작 필요")
    os._exit(2)
