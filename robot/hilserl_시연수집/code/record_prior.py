"""
HIL-SERL prior(시연) 데이터 녹화: VLA가 꽃 앞까지 간 자세에서 시작해서 사람이 게임패드로 줄기를 잡는다 (11-17).

왜: 실제 파이프라인은 SmolVLA(꽃 앞까지 가기) → HIL-SERL(잡기). 그래서 HIL-SERL 시연의 시작 자세는
"VLA가 끝난 자세"여야 함. 사람 시연의 끝 자세를 쓰면 VLA의 실제 오차(조금 덜 가거나 비껴 감)가 빠짐
→ 매 에피소드 실제로 VLA(서버 sior의 SmolVLA)를 돌려서 멈춘 자리에서 시연 시작.

한 에피소드:
  1. 시작 자세(trial4 데이터 첫 프레임 평균, start_pose_vla_trial4.json)로 이동, [대기] 꽃병 놓고 Start
  2. [VLA] 서버 SmolVLA가 지시문(꽃)대로 움직임. 멈추면(관절 명령 변화가 settle-s 동안 settle-deg 미만) 끝
     1·2·3·4 버튼은 0.4초 꾹 눌러야 동작 (ANALOG 꺼짐/전환 때 튀는 신호 무시). 버튼 = 일반 USB 패드 기준 (pad_map.json, 1~4 = 오른쪽 버튼 번호). 시작 자세로 갈 때·START 누를 때 그리퍼를 먼저 --vla-gripper 값으로 닫고 VLA 시작
     R1 = 지금 바로 사람이 넘겨받기, 2(B) = 이상한 데로 갈 때 취소 → VLA가 온 길을 거꾸로 되돌아가서 같은 꽃 다시
  3. [시연] 게임패드로 잡기. 이 구간만 녹화됨 (10 fps)
     왼쪽 스틱 = 앞뒤/좌우   오른쪽 스틱 위아래 = 높이   오른쪽 스틱 좌우 = 손목 회전
     R2 닫기 / L2 열기    1(Y) 성공 저장 / 3(A) 실패 저장 / 4(X) 버림(다시) / 2(B) VLA가 잘못 감 → 버리고 온 길로 되돌아감 / SELECT 버리고 종료
     시간 제한(--control-time-s) 넘기면 실패로 저장
  4. 그리퍼 열고 5 cm 올린 뒤 시작 자세로 복귀

기록 (lerobot 데이터셋, record_demos.py와 같은 키 + 손목 회전·카메라 2대):
  observation.state           관절 6개 (도, 그리퍼 0~100)
  observation.images.wrist    손목 카메라 Innomaker (VLA와 같은 카메라)
  observation.images.front    고정 카메라 C270
  action                      [delta_x, delta_y, delta_z, delta_roll, gripper]  (wrist_ee.py 참고)
  next.reward / next.done     성공(Y) 프레임 + 그 뒤 멈춘 --success-frames장(기본 15 = 1.5초) 전부 1 / 마지막 프레임 True
  complementary_info.discrete_penalty  항상 0
에피소드마다 <repo>_collection_log.jsonl에 꽃·배치·VLA 시간·VLA 종료 자세·결과를 남김.

준비 (Windows):
  1. smolvla_데이터수집/code/attach_usb.ps1 (로봇 WSL 연결 + 손목 카메라 송신기 -> 5558)
  2. python camera_sender_windows.py --find c270 --port 5559 --exposure -5   (고정 카메라)
  3. gamepad_sender.ps1 (게임패드 -> 5557)
  4. sior에서 policy 서버: bash ~/lerobot_flower/start_server.sh
사용 (WSL, conda env lerobot):
  python record_prior.py                         # 새 데이터셋
  python record_prior.py --resume                # 이어서
  python record_prior.py --layout "sunflower,blue,rose"   # 1·2·3번 칸 꽃 (기록용)
미리보기: Windows 브라우저 http://localhost:8080
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
import os
import threading
import time
from pathlib import Path
from queue import Queue

import cv2
import numpy as np

import lerobot_plugins  # noqa: F401
from lerobot_plugins import BUTTONS, RemoteGamepad, RemoteGamepadConfig
from net_camera import NetCamera
from usbip_camera import MjpegServer
from wrist_ee import ACTION_NAMES, GRIPPER_CLOSE, GRIPPER_OPEN, GRIPPER_STAY, WristEEController

from lerobot.async_inference import robot_client
from lerobot.async_inference.configs import RobotClientConfig
from lerobot.datasets import LeRobotDataset
from lerobot.robots.so_follower import SO101FollowerConfig
from lerobot.transport import services_pb2

HERE = Path(__file__).resolve().parent
SMOLVLA_CODE = HERE.parent.parent / "smolvla_데이터수집" / "code"
TASKS = {  # record_flower_reach.sh와 글자까지 같아야 함 (VLA 지시문)
    "rose": "Move the gripper close to the pink rose.",
    "blue": "Move the gripper close to the blue flower.",
    "sunflower": "Move the gripper close to the yellow sunflower.",
}
FLOWERS = list(TASKS)
DEFAULT_MODEL = os.environ.get("FLOWER_MODEL", "/home/sior/lerobot/outputs/train/smolvla_trial4_540_hold20_aug_snoise2_1122_1802/checkpoints/last/pretrained_model")  # 다른 서버면 FLOWER_MODEL로
MOVE_SPEED = 30.0  # 시작 자세 이동 속도 (deg/s)

GREEN, RED, YELLOW, WHITE = (0, 200, 0), (0, 0, 255), (0, 220, 255), (255, 255, 255)  # BGR
_status = ["", WHITE]


def set_status(text: str, color=WHITE) -> None:
    _status[0], _status[1] = text, color


def by_id(pattern: str, fallback: str) -> str:
    hits = sorted(glob.glob(pattern))
    return os.path.realpath(hits[0]) if hits else fallback


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--repo-id", default=os.environ.get("FLOWER_HF_USER", "parkjoonsang") + "/flower_hil_prior")
    p.add_argument("--root", type=Path, help="기본 ~/lerobot_data/<repo-id>")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--num-episodes", type=int, default=30, help="이번 세션 목표 (저장된 것 기준)")
    p.add_argument("--layout", default="", help='꽃병 1·2·3번 칸 꽃, 예 "sunflower,blue,rose" (로그에만 기록)')
    p.add_argument("--fps", type=int, default=10)
    p.add_argument("--control-time-s", type=float, default=60.0, help="시연 시간 제한 (11-22 사용자 요청 30 → 60초)")
    # VLA
    p.add_argument("--server", default=os.environ.get("FLOWER_SERVER", "100.120.78.64:8080"))
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--start-pose", type=Path, default=SMOLVLA_CODE / "start_pose_vla_trial4.json",
                   help="VLA 출발 자세 = trial4 첫 프레임 평균 (녹화용 start_pose.json보다 팔꿈치 +8°, 검증 66%%→92%%)")
    p.add_argument("--vla-gripper", type=float, default=69.0,
                   help="VLA 시작 전 그리퍼를 이 값으로 닫고 VLA 동안 고정. 0 = 끝까지 열림(약 115°), 100 = 닫힘 "
                        "(11-22 확인). 69 = 약 35° 열림 (사용자 요청, 처음 45°=60에서 줄임). trial4 데이터는 15.4 (약 97° 열림). "
                        "음수면 끔 (VLA 출력 그대로)")
    p.add_argument("--vla-gripper-state", type=float, default=15.9,
                   help="VLA에 보여 주는 그리퍼 상태값 (실제 그리퍼와 무관). trial4 학습 데이터 그리퍼 상태는 평균 15.9·표준편차 0.2라 "
                        "실제 69(35° 열림)를 그대로 넣으면 표준편차 265배 밖 입력이 돼서 VLA가 망가짐 (11-22 확인). 음수면 실제값")
    p.add_argument("--success-frames", type=int, default=15,
                   help="Y(성공) 뒤 그 자리에 멈춘 채 더 녹화할 프레임 수 (전부 reward 1, 마지막만 done). "
                        "보상 분류기 양성 사진이 에피소드당 1장뿐이던 문제 (11-22)")
    p.add_argument("--vla-min-s", type=float, default=2.0, help="이 시간 전에는 멈춤 판정 안 함")
    p.add_argument("--vla-max-s", type=float, default=15.0)
    p.add_argument("--settle-s", type=float, default=1.0)
    p.add_argument("--settle-deg", type=float, default=0.5)
    p.add_argument("--max-step-deg", type=float, default=10.0, help="한 스텝 관절 최대 이동 (안전 클리핑)")
    # 장치
    p.add_argument("--robot-port", default=by_id("/dev/serial/by-id/usb-1a86_*", "/dev/ttyACM0"))
    p.add_argument("--wrist-port", type=int, default=5558, help="손목 카메라 송신기 포트")
    p.add_argument("--front-port", type=int, default=5559, help="고정 카메라 송신기 포트")
    p.add_argument("--preview-port", type=int, default=8080)
    p.add_argument("--config", type=Path, default=HERE / "configs" / "flower_hil.json", help="게임패드·IK 설정")
    # 액션 크기 (actor도 같은 값을 써야 함)
    p.add_argument("--xyz-step", type=float, default=0.008, help="스틱 끝까지 = 스텝당 m (10 fps면 8 cm/s)")
    p.add_argument("--roll-step", type=float, default=6.0, help="스텝당 도")
    p.add_argument("--grip-step", type=float, default=10.0, help="스텝당 그리퍼 단위 (0~100)")
    return p.parse_args()


def move_smooth(robot, goal: dict, fps: int = 30, gripper_first: bool = False) -> None:
    """gripper_first: 그리퍼만 먼저 목표값으로 움직인 뒤 팔 이동 (11-22 사용자 요청: 닫고 나서 이동)."""
    names = list(robot.bus.motors)
    if gripper_first and "gripper" in goal:
        cur = robot.bus.sync_read("Present_Position")
        move_smooth(robot, {**{n: float(cur[n]) for n in names}, "gripper": goal["gripper"]}, fps)
        time.sleep(0.2)
    cur = robot.bus.sync_read("Present_Position")
    begin = np.array([cur[n] for n in names], dtype=float)
    end = np.array([goal[n] for n in names], dtype=float)
    n_steps = max(1, int(max(1.0, np.abs(end - begin).max() / MOVE_SPEED) * fps))
    for i in range(1, n_steps + 1):
        a = i / n_steps
        a = a * a * (3 - 2 * a)
        robot.bus.sync_write("Goal_Position", dict(zip(names, begin + a * (end - begin), strict=True)))
        time.sleep(1 / fps)


def rewind(robot, names, history: list, q_from: np.ndarray, grip: float | None, fps: int, speed: int = 2) -> None:
    """VLA가 엉뚱한 데로 갔을 때 (11-22 사용자 요청): VLA가 보낸 관절 명령을 거꾸로 재생해서 온 길로 되돌아감.
    시작 자세로 바로 직선 이동하면 꽃병·줄기를 쓸고 지나갈 수 있어서. q_from = 지금 자세 (시연 중 움직였으면 먼저 VLA 끝 자세로)."""
    if not history:
        return
    path = [q for _, q in history][::-1][::speed]  # speed배 빠르게
    path = [np.asarray(q, float).copy() for q in path]
    if grip is not None:
        for q in path:
            q[5] = grip
    cur = np.asarray(q_from, float)
    first = path[0]
    n = max(1, int(np.abs(first - cur).max() / MOVE_SPEED * fps) + 1)
    for i in range(1, n + 1):  # 지금 자세 → 재생 시작점 (VLA 끝 자세)
        robot.bus.sync_write("Goal_Position", dict(zip(names, cur + i / n * (first - cur), strict=True)))
        time.sleep(1 / fps)
    for q in path:
        robot.bus.sync_write("Goal_Position", dict(zip(names, q, strict=True)))
        time.sleep(1 / fps)


HOLD_S = 0.4  # 저장·되돌리기 버튼은 이만큼 꾹 눌러야 동작


def held(pad: RemoteGamepad, name: str, hold_s: float = HOLD_S) -> bool:
    """버튼을 hold_s초 이상 계속 눌렀을 때만 True (11-22).
    일반 USB 패드는 ANALOG가 꺼져 있으면 오른쪽 스틱이 버튼 1~4로 들어오고, ANALOG를 누르는 순간에도
    버튼 신호가 튐 → 1(성공)/3(실패)이 저절로 눌려 저장되던 문제. 순간 신호는 짧아서 걸러짐."""
    if not pad.pop_pressed(name):
        return False
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < hold_s:
        s = pad._live_state()
        if s is None or not (int(s.get("btn", 0)) & BUTTONS[name]):
            print(f"   ({name} 버튼이 짧게 눌림 -> 무시. {hold_s}초 꾹 누르기)")
            return False
        time.sleep(0.02)
    return True


def log_vla_fail(fail_dir: Path, rec: dict, wrist_img, front_img) -> None:
    """VLA가 잘못 간 경우(2번 되돌리기) 기록: <repo>_vla_fail/log.jsonl + 그 순간 손목·고정 카메라 사진."""
    fail_dir.mkdir(parents=True, exist_ok=True)
    stem = time.strftime("%m%d_%H%M%S")
    for tag, img in (("wrist", wrist_img), ("front", front_img)):
        if img is not None:
            cv2.imwrite(str(fail_dir / f"{stem}_{tag}.jpg"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    rec = {**rec, "image": stem, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    with (fail_dir / "log.jsonl").open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    n = sum(1 for _ in (fail_dir / "log.jsonl").open())
    print(f"   [VLA 실패 기록 {n}개째] {fail_dir.name}/{stem}_*.jpg")


LOW_VOLT = 6.6  # 이 아래면 배터리 교체 (11-22: 6.0V대에서 큰 관절 모터가 멈춤)


def read_volt(robot) -> float | None:
    """모터 전압 중 가장 낮은 값(V). 대기 중(VLA 스레드 멈춘 뒤)에만 부를 것. 실패하면 None."""
    try:
        return min(robot.bus.read("Present_Voltage", m, normalize=False) / 10 for m in robot.bus.motors)
    except Exception:
        return None


def read_q(robot, names) -> np.ndarray:
    cur = robot.bus.sync_read("Present_Position")
    return np.array([cur[n] for n in names], dtype=float)


def hold_here(robot) -> np.ndarray:
    cur = robot.bus.sync_read("Present_Position")
    robot.bus.sync_write("Goal_Position", cur)
    return np.array(list(cur.values()), dtype=float)


def pad_action(pad: RemoteGamepad, tcfg: dict) -> np.ndarray:
    """게임패드 → [dx, dy, dz, droll, gripper]. 패드 끊김이면 정지 액션."""
    s = pad._live_state()
    if s is None:
        return np.array([0, 0, 0, 0, GRIPPER_STAY], dtype=np.float32)

    def dz(v):
        return 0.0 if abs(v) < tcfg["deadzone"] else float(np.clip(v, -1, 1))

    close, open_ = s.get("rt", 0.0) > 0.5, s.get("lt", 0.0) > 0.5
    if tcfg["swap_gripper"]:
        close, open_ = open_, close
    g = GRIPPER_CLOSE if close and not open_ else GRIPPER_OPEN if open_ and not close else GRIPPER_STAY
    return np.array([
        tcfg["x_sign"] * dz(s.get("ly", 0.0)),   # 왼쪽 스틱 위 = 앞
        tcfg["y_sign"] * -dz(s.get("lx", 0.0)),  # 왼쪽 스틱 왼쪽 = +y
        tcfg["z_sign"] * dz(s.get("ry", 0.0)),   # 오른쪽 스틱 위 = 위
        dz(s.get("rx", 0.0)),                    # 오른쪽 스틱 좌우 = 손목 회전
        g,
    ], dtype=np.float32)


class Vla:
    """RobotClient 하나를 에피소드마다 다시 씀 (모델은 서버에 한 번만 올림)."""

    def __init__(self, args, wrist: NetCamera):
        orig = robot_client.make_robot_from_config

        def make_robot(cfg):
            robot = orig(cfg)
            robot.cameras = {"camera1": wrist}  # 학습 때 front -> camera1 매핑. connect 전에 바꿔야 함
            return robot

        robot_client.make_robot_from_config = make_robot
        cfg = RobotClientConfig(
            policy_type="smolvla", pretrained_name_or_path=args.model,
            robot=SO101FollowerConfig(port=args.robot_port, id="my_follower_arm",
                                      max_relative_target=args.max_step_deg, disable_torque_on_disconnect=False),
            actions_per_chunk=50, task=TASKS["rose"], server_address=args.server, policy_device="cuda",
            chunk_size_threshold=0.5, fps=args.fps,
        )
        self.client = robot_client.RobotClient(cfg)  # 로봇 + 손목 카메라 연결
        self.robot = self.client.robot
        self.names = list(self.robot.bus.motors)
        self.history: list[tuple[float, np.ndarray]] = []
        orig_send = self.robot.send_action

        grip = args.vla_gripper if args.vla_gripper >= 0 else None

        def send_tap(action):  # VLA가 보내는 관절 명령을 기록 (멈춤 판정용. 버스는 VLA 스레드만 씀)
            if grip is not None:  # 사용자 요청 (11-22): VLA 동안 그리퍼를 조금 닫은 값으로 고정
                action = {**action, "gripper.pos": grip}
            self.history.append((time.perf_counter(), np.array([action[f"{n}.pos"] for n in self.names])))
            return orig_send(action)

        self.robot.send_action = send_tap

        orig_obs = self.robot.get_observation
        grip_state = args.vla_gripper_state if args.vla_gripper_state >= 0 else None

        def obs_tap():  # VLA 입력의 그리퍼 상태만 학습 때 값으로 (녹화는 bus.sync_read라 영향 없음)
            o = orig_obs()
            if grip_state is not None:
                o["gripper.pos"] = grip_state
            return o

        self.robot.get_observation = obs_tap

    def load(self) -> bool:
        print(f"[VLA] 서버 {self.client.server_address} 연결 + 모델 로딩 (처음 한 번)...")
        return self.client.start()

    def run(self, task: str, args, pad: RemoteGamepad) -> tuple[str, float]:
        """VLA 실행. (멈춘 이유, 실행 시간) 반환. 이유: settled / timeout / takeover / abort / pad_lost / error"""
        c = self.client
        c.stub.Ready(services_pb2.Empty())  # 서버 상태(지난 에피소드 timestep) 초기화. 모델은 그대로
        with c.action_queue_lock:
            c.action_queue = Queue()
        with c.latest_action_lock:
            c.latest_action = -1
        c.must_go.set()
        c.start_barrier = threading.Barrier(2)
        c.shutdown_event.clear()
        self.history = []
        recv = threading.Thread(target=c.receive_actions, daemon=True)
        ctrl = threading.Thread(target=c.control_loop, kwargs={"task": task}, daemon=True)
        recv.start()
        ctrl.start()
        t0 = time.perf_counter()
        reason = "timeout"
        pad.clear_pressed()
        while True:
            time.sleep(0.05)
            el = time.perf_counter() - t0
            set_status(f"VLA {el:4.1f}s  R1=take over  hold 2=rewind", YELLOW)
            if pad.pop_pressed("rb"):
                reason = "takeover"
                break
            if held(pad, "b"):
                reason = "abort"
                break
            if not pad.is_live():
                reason = "pad_lost"
                break
            if not ctrl.is_alive():
                reason = "error"
                break
            if el >= args.vla_max_s:
                break
            if el >= args.vla_min_s and self.history:
                recent = [q for t, q in self.history if t >= time.perf_counter() - args.settle_s]
                window_full = self.history[0][0] <= time.perf_counter() - args.settle_s
                if window_full and (not recent or np.ptp(np.stack(recent), axis=0).max() < args.settle_deg):
                    reason = "settled"
                    break
        c.shutdown_event.set()
        ctrl.join(timeout=3)
        recv.join(timeout=5)  # 서버 GetActions가 obs 대기 timeout(약 2 s)으로 돌아올 때까지
        if recv.is_alive() or ctrl.is_alive():
            print("⚠️ VLA 스레드가 아직 안 끝남 (다음 에피소드에 영향 가능)")
        return reason, time.perf_counter() - t0


def build_features(state_dim: int, h: int, w: int) -> dict:
    img = {"dtype": "video", "shape": (h, w, 3), "names": ["height", "width", "channels"]}
    return {
        "observation.state": {"dtype": "float32", "shape": (state_dim,), "names": None},
        "observation.images.wrist": img,
        "observation.images.front": dict(img),
        "action": {"dtype": "float32", "shape": (len(ACTION_NAMES),), "names": ACTION_NAMES},
        "next.reward": {"dtype": "float32", "shape": (1,), "names": None},
        "next.done": {"dtype": "bool", "shape": (1,), "names": None},
        "complementary_info.discrete_penalty": {"dtype": "float32", "shape": (1,), "names": ["discrete_penalty"]},
    }


def main():
    args = parse_args()
    raw = json.loads(args.config.read_text())
    tcfg = raw["env"]["teleop"]
    ikcfg = raw["env"]["processor"]["inverse_kinematics"]
    bounds = ikcfg.get("end_effector_bounds")
    root = args.root or Path.home() / "lerobot_data" / args.repo_id
    log_path = root.parent / f"{root.name}_collection_log.jsonl"
    vla_fail_dir = root.parent / f"{root.name}_vla_fail"  # VLA가 잘못 간 경우 기록 (11-22 사용자 요청)
    if not args.resume and root.exists():
        saved = list(root.glob("data/*/*.parquet"))
        if saved:
            raise FileExistsError(f"{root} 에 저장된 에피소드가 있음. 이어서 하려면 --resume")
        # 저장된 에피소드 없이 멈춘 폴더(meta·임시 이미지만)는 지우고 새로 시작 (11-22)
        print(f"저장된 에피소드 없는 폴더 {root} → 지우고 새로 시작")
        shutil.rmtree(root)
        log_path.unlink(missing_ok=True)
    start_pose = json.loads(args.start_pose.read_text())
    if args.vla_gripper >= 0:
        start_pose["gripper"] = args.vla_gripper  # 시작 자세로 갈 때 그리퍼 먼저 닫고(gripper_first) 팔 이동

    # ---- 장치 ----
    pad = RemoteGamepad(RemoteGamepadConfig(port=tcfg["port"], deadzone=tcfg["deadzone"], always_intervene=True))
    pad.connect()
    front = NetCamera(port=args.front_port)
    front.connect()
    wrist = NetCamera(port=args.wrist_port)
    vla = Vla(args, wrist)  # 로봇 + 손목 카메라 연결
    robot, names = vla.robot, vla.names
    ctrl = WristEEController(str(HERE / ikcfg["urdf_path"]), ikcfg["target_frame_name"], names,
                             xyz_step=args.xyz_step, roll_step=args.roll_step, grip_step=args.grip_step, bounds=bounds)

    preview = MjpegServer(port=args.preview_port, fps=15)
    stop_preview = threading.Event()

    def preview_loop():
        while not stop_preview.is_set():
            try:
                tiles = []
                for cam in (wrist, front):
                    try:
                        tiles.append(cv2.cvtColor(cam.read_latest(1000), cv2.COLOR_RGB2BGR))
                    except Exception:
                        tiles.append(np.zeros((480, 640, 3), np.uint8))
                img = np.hstack(tiles)
                cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
                cv2.putText(img, _status[0], (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, _status[1], 2)
                preview.update_bgr(img)
            except Exception:
                pass
            time.sleep(1 / 15)

    threading.Thread(target=preview_loop, daemon=True).start()
    print(f"미리보기: Windows 브라우저 http://localhost:{args.preview_port}  (왼쪽 손목 / 오른쪽 고정)")

    dataset = None
    try:
        set_status("LOADING VLA", YELLOW)
        if not vla.load():
            raise ConnectionError("policy 서버 연결 실패 (sior에서 start_server.sh, 포트 8080 확인)")
        if args.resume:
            dataset = LeRobotDataset.resume(args.repo_id, root=root, image_writer_threads=4)
        else:
            dataset = LeRobotDataset.create(args.repo_id, args.fps, root=root, robot_type="so101_follower",
                                            use_videos=True, image_writer_threads=4,
                                            features=build_features(len(names), wrist.height, wrist.width))
        log = [json.loads(line) for line in log_path.read_text().splitlines()] if log_path.exists() else []
        target = dataset.num_episodes + args.num_episodes
        print(f"데이터셋 {root} (기존 {dataset.num_episodes}개, 이번 목표 {args.num_episodes}개)")
        quit_all = False
        retry_flower = None
        analog_ok = False  # 오른쪽 스틱 아날로그 값이 한 번이라도 보이면 True (ANALOG 꺼진 채 녹화 방지)

        while dataset.num_episodes < target and not quit_all:
            ep = dataset.num_episodes
            # ---- 시작 자세 + 대기 ----
            set_status("MOVING TO START", YELLOW)
            move_smooth(robot, start_pose, gripper_first=True)
            counts = {f: sum(1 for r in log if r["flower"] == f) for f in FLOWERS}
            flower = retry_flower or min(FLOWERS, key=lambda f: counts[f])  # 되돌아온 경우 같은 꽃, 아니면 가장 적게 모인 꽃
            retry_flower = None
            pad.clear_pressed()
            volt = read_volt(robot)
            vtxt = "?" if volt is None else f"{volt:.1f}V"
            print(f"\n[대기] ep{ep}  꽃 {flower}  (모은 수 {counts})  배터리 {vtxt}  START=시작  L1=꽃 바꾸기  SELECT=종료")
            if volt is not None and volt < LOW_VOLT:
                print(f"   ⚠️ 배터리 {volt:.1f}V < {LOW_VOLT}V -> 교체하세요 (모터가 멈출 수 있음)")
            if not analog_ok:
                print("   ANALOG 확인: 패드 ANALOG 불 켜고 오른쪽 스틱을 한 번 끝까지 밀어 주세요 (확인 전엔 START 안 먹음)")
            while True:
                if not analog_ok:
                    st = pad._live_state() or {}
                    if max(abs(float(st.get("rx", 0.0))), abs(float(st.get("ry", 0.0)))) > 0.5:
                        analog_ok = True
                        print("   ANALOG 확인됨")
                if not analog_ok:
                    set_status(f"ANALOG? turn on + move RIGHT stick  ep{ep} [{flower}]  {vtxt}", YELLOW)
                    pad.pop_pressed("start")  # 확인 전 START는 버림
                else:
                    low = volt is not None and volt < LOW_VOLT
                    set_status(f"READY ep{ep} [{flower}]  {'LOW BATTERY ' if low else ''}{vtxt}  START=go  L1=flower  SELECT=quit",
                               RED if low else WHITE)
                if pad.pop_pressed("back"):
                    quit_all = True
                    break
                if pad.pop_pressed("lb"):
                    flower = FLOWERS[(FLOWERS.index(flower) + 1) % len(FLOWERS)]
                    print(f"   꽃 -> {flower}")
                if pad.pop_pressed("start"):
                    break
                time.sleep(0.05)
            if quit_all:
                break

            # ---- 그리퍼 먼저 닫기 (11-22 사용자 요청: Start 누르면 닫고 나서 이동) ----
            grip_fix = args.vla_gripper if args.vla_gripper >= 0 else None
            if grip_fix is not None:
                set_status(f"GRIPPER -> {grip_fix:.1f}", YELLOW)
                move_smooth(robot, {**dict(zip(names, read_q(robot, names))), "gripper": grip_fix})
                time.sleep(0.3)  # 손목 화면에 닫힌 그리퍼가 잡힌 뒤 VLA 시작

            # ---- VLA ----
            print(f"[VLA] {TASKS[flower]}")
            reason, vla_s = vla.run(TASKS[flower], args, pad)
            q0 = hold_here(robot)
            print(f"   VLA 끝: {reason}, {vla_s:.1f}s")
            if reason in ("abort", "pad_lost", "error"):
                print("   이 에피소드 취소 -> 온 길로 되돌아감 -> 시작 자세 (같은 꽃 다시)")
                if reason == "abort":  # 사람이 2번으로 취소 = VLA가 잘못 가는 중
                    log_vla_fail(vla_fail_dir, {"flower": flower, "task": TASKS[flower], "layout": args.layout,
                                                "when": "during_vla", "vla_s": round(vla_s, 2),
                                                "q": [round(float(v), 2) for v in q0]},
                                 wrist.read_latest(), front.read_latest())
                set_status("REWIND (VLA path reversed)", YELLOW)
                rewind(robot, names, vla.history, q0, grip_fix, args.fps)
                retry_flower = flower
                continue

            # ---- 시연 녹화 ----
            ctrl.reset_from(q0)
            pad.clear_pressed()
            print("[시연] (0.4초 꾹) 1 성공 / 3 실패 / 4 다시 / 2 VLA 잘못 감(되돌아가기) / SELECT 버리고 종료   그리퍼 R2 닫기 / L2 열기")
            t0 = time.perf_counter()
            result = None
            while True:
                step_t = time.perf_counter()
                if pad.pop_pressed("back"):
                    quit_all = True
                    break
                if held(pad, "x"):
                    result = "rerecord"
                    break
                if held(pad, "b"):  # VLA가 잘못 간 걸 시연 중에 알았을 때: 버리고 온 길로 되돌아가서 같은 꽃 다시
                    result = "vla_wrong"
                    break
                state = read_q(robot, names).astype(np.float32)
                img_w, img_f = wrist.read_latest(), front.read_latest()
                action = pad_action(pad, tcfg)
                q_cmd = ctrl.step(action)
                robot.bus.sync_write("Goal_Position", dict(zip(names, q_cmd, strict=True)))
                success = held(pad, "y")
                failure = not success and held(pad, "a")
                el = time.perf_counter() - t0
                timeout = el >= args.control_time_s
                done = (success and args.success_frames <= 0) or failure or timeout

                def frame(st, iw, ifr, act, rew, dn):
                    return {
                        "observation.state": st,
                        "observation.images.wrist": iw,
                        "observation.images.front": ifr,
                        "action": act,
                        "next.reward": np.array([rew], np.float32),
                        "next.done": np.array([dn], bool),
                        "complementary_info.discrete_penalty": np.zeros(1, np.float32),
                        "task": TASKS[flower],
                    }

                dataset.add_frame(frame(state, img_w, img_f, action, 1.0 if success else 0.0, done))
                set_status(f"REC ep{ep} {el:4.1f}/{args.control_time_s:.0f}s  hold 1=ok 3=fail 4=redo 2=rewind  {ctrl.blocked}", RED)
                if success and not done:
                    # 성공 뒤: 그 자리에 멈춘 채(정지 액션) success_frames장 더 녹화, 전부 reward 1, 마지막만 done
                    stay = np.array([0, 0, 0, 0, GRIPPER_STAY], dtype=np.float32)
                    for k in range(args.success_frames):
                        time.sleep(1 / args.fps)
                        set_status(f"SUCCESS HOLD {k + 1}/{args.success_frames}  (don't touch)", YELLOW)
                        robot.bus.sync_write("Goal_Position", dict(zip(names, ctrl.step(stay), strict=True)))
                        dataset.add_frame(frame(read_q(robot, names).astype(np.float32), wrist.read_latest(),
                                                front.read_latest(), stay, 1.0, k == args.success_frames - 1))
                    done = True
                if done:
                    result = "success" if success else "failure"
                    break
                time.sleep(max(0.0, 1 / args.fps - (time.perf_counter() - step_t)))

            if result in ("success", "failure"):
                set_status(f"SAVING ep{ep}", YELLOW)
                dataset.save_episode()
                rec = {"episode_index": ep, "flower": flower, "task": TASKS[flower], "layout": args.layout,
                       "result": result, "vla_stop": reason, "vla_s": round(vla_s, 2),
                       "vla_end_q": [round(float(v), 2) for v in q0], "demo_s": round(time.perf_counter() - t0, 2),
                       "time": time.strftime("%Y-%m-%d %H:%M:%S")}
                log.append(rec)
                with log_path.open("a") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"   [저장] ep{ep} {result} (총 {dataset.num_episodes}개)")
            else:
                dataset.clear_episode_buffer()
                print("   [버림]")
            if result == "vla_wrong":
                print("   VLA 잘못 감 -> 온 길로 되돌아감 -> 시작 자세 (같은 꽃 다시)")
                log_vla_fail(vla_fail_dir, {"flower": flower, "task": TASKS[flower], "layout": args.layout,
                                            "when": "after_vla", "vla_stop": reason, "vla_s": round(vla_s, 2),
                                            "q": [round(float(v), 2) for v in q0]},  # q = VLA가 멈춘 자세
                             wrist.read_latest(), front.read_latest())
                set_status("REWIND (VLA path reversed)", YELLOW)
                rewind(robot, names, vla.history, read_q(robot, names), grip_fix, args.fps)
                retry_flower = flower
                continue

            # ---- 놓고 올리기 → 시작 자세 ----
            set_status("RELEASE + LIFT", YELLOW)
            for a in [[0, 0, 0, 0, GRIPPER_OPEN]] * 6 + [[0, 0, 0.8, 0, GRIPPER_STAY]] * 8:
                robot.bus.sync_write("Goal_Position", dict(zip(names, ctrl.step(a), strict=True)))
                time.sleep(1 / args.fps)

    except KeyboardInterrupt:
        print("\n[Ctrl+C] 녹화 중이던 에피소드는 버림")
        if dataset is not None:
            dataset.clear_episode_buffer()
    finally:
        set_status("STOPPED", WHITE)
        vla.client.shutdown_event.set()
        try:
            hold_here(robot)
        except Exception:
            pass
        if dataset is not None:
            dataset.finalize()
            print(f"\n종료. {root}  총 {dataset.num_episodes}개")
        stop_preview.set()
        pad.disconnect()
        front.disconnect()
        try:
            vla.client.stop()  # 로봇·손목 카메라 연결 끊기 (토크 유지)
        except Exception as e:
            print(f"⚠️ 종료 중 에러 (무시): {e}")


if __name__ == "__main__":
    main()
