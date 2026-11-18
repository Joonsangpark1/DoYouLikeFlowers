"""
HIL-SERL prior(시연) 데이터 녹화: VLA가 꽃 앞까지 간 자세에서 시작해서 사람이 게임패드로 줄기를 잡는다 (11-17).

왜: 실제 파이프라인은 SmolVLA(꽃 앞까지 가기) → HIL-SERL(잡기). 그래서 HIL-SERL 시연의 시작 자세는
"VLA가 끝난 자세"여야 함. 사람 시연의 끝 자세를 쓰면 VLA의 실제 오차(조금 덜 가거나 비껴 감)가 빠짐
→ 매 에피소드 실제로 VLA(서버 sior의 SmolVLA)를 돌려서 멈춘 자리에서 시연 시작.

한 에피소드:
  1. 시작 자세(trial4 데이터 첫 프레임 평균, start_pose_vla_trial4.json)로 이동, [대기] 꽃병 놓고 Start
  2. [VLA] 서버 SmolVLA가 지시문(꽃)대로 움직임. 멈추면(관절 명령 변화가 settle-s 동안 settle-deg 미만) 끝
     RB = 지금 바로 사람이 넘겨받기, B = 이 에피소드 취소(이상한 데로 갈 때)
  3. [시연] 게임패드로 잡기. 이 구간만 녹화됨 (10 fps)
     왼쪽 스틱 = 앞뒤/좌우   오른쪽 스틱 위아래 = 높이   오른쪽 스틱 좌우 = 손목 회전
     RT 닫기 / LT 열기    Y 성공 저장 / A 실패 저장 / X 버림(다시) / Back 버리고 종료
     시간 제한(--control-time-s) 넘기면 실패로 저장
  4. 그리퍼 열고 5 cm 올린 뒤 시작 자세로 복귀

기록 (lerobot 데이터셋, record_demos.py와 같은 키 + 손목 회전·카메라 2대):
  observation.state           관절 6개 (도, 그리퍼 0~100)
  observation.images.wrist    손목 카메라 Innomaker (VLA와 같은 카메라)
  observation.images.front    고정 카메라 C270
  action                      [delta_x, delta_y, delta_z, delta_roll, gripper]  (wrist_ee.py 참고)
  next.reward / next.done     성공(Y) 프레임 1 / 마지막 프레임 True
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
import os
import threading
import time
from pathlib import Path
from queue import Queue

import cv2
import numpy as np

import lerobot_plugins  # noqa: F401
from lerobot_plugins import RemoteGamepad, RemoteGamepadConfig
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
DEFAULT_MODEL = "/home/sior/lerobot/outputs/train/smolvla_trial4_1117_1811/checkpoints/last/pretrained_model"
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
    p.add_argument("--repo-id", default="parkjoonsang/flower_hil_prior")
    p.add_argument("--root", type=Path, help="기본 ~/lerobot_data/<repo-id>")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--num-episodes", type=int, default=30, help="이번 세션 목표 (저장된 것 기준)")
    p.add_argument("--layout", default="", help='꽃병 1·2·3번 칸 꽃, 예 "sunflower,blue,rose" (로그에만 기록)')
    p.add_argument("--fps", type=int, default=10)
    p.add_argument("--control-time-s", type=float, default=30.0, help="시연 시간 제한")
    # VLA
    p.add_argument("--server", default="100.120.78.64:8080")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--start-pose", type=Path, default=SMOLVLA_CODE / "start_pose_vla_trial4.json",
                   help="VLA 출발 자세 = trial4 첫 프레임 평균 (녹화용 start_pose.json보다 팔꿈치 +8°, 검증 66%%→92%%)")
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


def move_smooth(robot, goal: dict, fps: int = 30) -> None:
    names = list(robot.bus.motors)
    cur = robot.bus.sync_read("Present_Position")
    begin = np.array([cur[n] for n in names], dtype=float)
    end = np.array([goal[n] for n in names], dtype=float)
    n_steps = max(1, int(max(1.0, np.abs(end - begin).max() / MOVE_SPEED) * fps))
    for i in range(1, n_steps + 1):
        a = i / n_steps
        a = a * a * (3 - 2 * a)
        robot.bus.sync_write("Goal_Position", dict(zip(names, begin + a * (end - begin), strict=True)))
        time.sleep(1 / fps)


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

        def send_tap(action):  # VLA가 보내는 관절 명령을 기록 (멈춤 판정용. 버스는 VLA 스레드만 씀)
            self.history.append((time.perf_counter(), np.array([action[f"{n}.pos"] for n in self.names])))
            return orig_send(action)

        self.robot.send_action = send_tap

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
            set_status(f"VLA {el:4.1f}s  RB=take over  B=cancel", YELLOW)
            if pad.pop_pressed("rb"):
                reason = "takeover"
                break
            if pad.pop_pressed("b"):
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
    if not args.resume and root.exists():
        raise FileExistsError(f"{root} 가 이미 있음. 이어서 하려면 --resume")
    start_pose = json.loads(args.start_pose.read_text())

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

        while dataset.num_episodes < target and not quit_all:
            ep = dataset.num_episodes
            # ---- 시작 자세 + 대기 ----
            set_status("MOVING TO START", YELLOW)
            move_smooth(robot, start_pose)
            counts = {f: sum(1 for r in log if r["flower"] == f) for f in FLOWERS}
            flower = min(FLOWERS, key=lambda f: counts[f])  # 가장 적게 모인 꽃
            pad.clear_pressed()
            print(f"\n[대기] ep{ep}  꽃 {flower}  (모은 수 {counts})  Start=시작  LB=꽃 바꾸기  Back=종료")
            while True:
                set_status(f"READY ep{ep} [{flower}]  Start=go  LB=flower  Back=quit", WHITE)
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

            # ---- VLA ----
            print(f"[VLA] {TASKS[flower]}")
            reason, vla_s = vla.run(TASKS[flower], args, pad)
            q0 = hold_here(robot)
            print(f"   VLA 끝: {reason}, {vla_s:.1f}s")
            if reason in ("abort", "pad_lost", "error"):
                print("   이 에피소드 취소 -> 시작 자세로")
                continue

            # ---- 시연 녹화 ----
            ctrl.reset_from(q0)
            pad.clear_pressed()
            print("[시연] Y 성공 / A 실패 / X 다시 / Back 버리고 종료")
            t0 = time.perf_counter()
            result = None
            while True:
                step_t = time.perf_counter()
                if pad.pop_pressed("back"):
                    quit_all = True
                    break
                if pad.pop_pressed("x"):
                    result = "rerecord"
                    break
                state = read_q(robot, names).astype(np.float32)
                img_w, img_f = wrist.read_latest(), front.read_latest()
                action = pad_action(pad, tcfg)
                q_cmd = ctrl.step(action)
                robot.bus.sync_write("Goal_Position", dict(zip(names, q_cmd, strict=True)))
                success, failure = pad.pop_pressed("y"), pad.pop_pressed("a")
                el = time.perf_counter() - t0
                timeout = el >= args.control_time_s
                done = success or failure or timeout
                dataset.add_frame({
                    "observation.state": state,
                    "observation.images.wrist": img_w,
                    "observation.images.front": img_f,
                    "action": action,
                    "next.reward": np.array([1.0 if success else 0.0], np.float32),
                    "next.done": np.array([done], bool),
                    "complementary_info.discrete_penalty": np.zeros(1, np.float32),
                    "task": TASKS[flower],
                })
                set_status(f"REC ep{ep} {el:4.1f}/{args.control_time_s:.0f}s  Y=ok A=fail X=redo  {ctrl.blocked}", RED)
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
