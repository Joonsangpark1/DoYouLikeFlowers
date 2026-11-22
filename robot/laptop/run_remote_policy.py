"""
노트북(로봇+카메라)에서 실행하는 원격 추론 클라이언트. 연산은 데스크탑 GPU의 serve_policy.py가 하고,
노트북은 관측을 보내고 받은 행동 묶음을 30fps로 실행만 한다.

lerobot 공식 async_inference RobotClient를 그대로 쓰되 두 가지만 바꾼다:
  1. 카메라: 공식 클라이언트는 lerobot 기본 OpenCVCamera로 열어서 WSL+usbipd에서 'Bad file descriptor'
     -> 로봇을 만든 직후 카메라를 usbip_camera.UsbipOpenCVCamera로 끼워 넣는다
  2. 카메라 이름: 공식 클라이언트는 rename_map을 서버에 안 넘긴다. 학습 때 front -> camera1로 매핑했으므로
     처음부터 camera1이라는 이름으로 보낸다

안전장치:
  - 시작 전에 start_pose.json 자세로 천천히 이동
  - max_relative_target: 한 스텝에 관절이 이 각도 이상 못 움직이게 클리핑 (모델이 이상한 값을 내도 급격히 안 튐)
  - 종료 시 토크 유지 (disable_torque_on_disconnect=False) -> 팔이 떨어지지 않음
  - ESC / Space: 즉시 정지

사용 예:
  python run_remote_policy.py --task 1        # 1=핑크 장미, 2=노란 해바라기
  python run_remote_policy.py --task 2 --model /home/sior/lerobot/outputs/train/smolvla_flower_reach/checkpoints/002000/pretrained_model

미리보기: Windows 브라우저에서 http://localhost:8080
"""
from __future__ import annotations

import argparse
import os
import json
import select
import sys
import termios
import threading
import time
import tty
from pathlib import Path

from lerobot.async_inference import robot_client
from lerobot.async_inference.configs import RobotClientConfig
from lerobot.cameras import ColorMode
from lerobot.cameras.opencv import OpenCVCameraConfig
from lerobot.robots.so_follower import SO101FollowerConfig

from usbip_camera import MjpegServer, UsbipOpenCVCamera

import sys as _sys
_sys.path.insert(0, "/mnt/c/Users/A/Desktop/로보틱스/smolvla_데이터수집/code")
from net_camera import NetCamera  # noqa: E402  Windows camera_sender_windows.py가 보내는 사진 (trial4 녹화와 같은 경로)

ROBOT_PORT = "/dev/ttyACM0"
ROBOT_ID = "my_follower_arm"
CAMERA_PATH = "/dev/video0"
CAMERA_NAME = "camera1"  # 학습 때 rename_map으로 front -> camera1 이었으므로 처음부터 이 이름으로 보냄
CAM_WIDTH, CAM_HEIGHT = 640, 480
HTTP_PORT = 8080

TASKS = {
    "1": "Move the gripper close to the pink rose.",
    "2": "Move the gripper close to the yellow sunflower.",
    # trial3 (11-16~): 꽃 이름으로. 지시문은 record_flower_reach.sh와 글자까지 같아야 함
    "rose": "Move the gripper close to the pink rose.",
    "blue": "Move the gripper close to the blue flower.",
    "sunflower": "Move the gripper close to the yellow sunflower.",
}
DEFAULT_MODEL = os.environ.get("FLOWER_MODEL", "/home/sior/lerobot/outputs/train/smolvla_trial4_1117_1811/checkpoints/last/pretrained_model")  # 다른 서버면 FLOWER_MODEL로
# trial4 데이터 첫 프레임 상태 평균 (11-18). 녹화 start_pose.json은 토크를 풀면 팔꿈치가 약 8° 처져서 데이터와 다름
#   오프라인 검증: start_pose.json 상태로 넣으면 꽃 고르기 66%, 이 평균이면 92% (eval_trial4.py)
DEFAULT_START_POSE = Path("/mnt/c/Users/A/Desktop/로보틱스/smolvla_데이터수집/code/start_pose_vla_trial4.json")


def _by_id(pattern: str, fallback: str) -> str:
    """usbip 재연결마다 /dev 번호가 바뀌므로 장치 고정 이름으로 현재 경로를 찾음."""
    import glob
    import os
    hits = sorted(glob.glob(pattern))
    return os.path.realpath(hits[0]) if hits else fallback
MOVE_SPEED = 30.0  # 시작 자세로 이동 속도 (deg/s)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True, help="rose / blue / sunflower (trial3), 1/2 (옛 지시문), 또는 지시문 문장 그대로")
    p.add_argument("--server", default=os.environ.get("FLOWER_SERVER", "100.120.78.64:8080"), help="sior policy 서버 주소 (Tailscale IP:포트, 11-15 IP 변경)")
    p.add_argument("--camera", default=_by_id("/dev/v4l/by-id/*Innomaker*-video-index0", CAMERA_PATH))
    p.add_argument("--robot-port", default=_by_id("/dev/serial/by-id/usb-1a86_*", ROBOT_PORT))
    p.add_argument("--model", default=DEFAULT_MODEL, help="체크포인트 경로 (서버=데스크탑 기준) 또는 HF 모델 repo id")
    p.add_argument("--fps", type=int, default=10, help="데이터셋 fps와 같게 (trial3 = 10)")
    p.add_argument("--actions-per-chunk", type=int, default=50)
    p.add_argument("--chunk-threshold", type=float, default=0.5, help="남은 행동이 이 비율 이하면 새 관측 전송")
    # 11-18: 10 → 20. 10이면 시작 직후부터 어깨·손목 명령이 계속 잘려서 팔이 모델을 못 따라감
    #   (trial4 데이터에서 명령-실제 차이 99%: 어깨 13°, 손목 19°, 손목 10° 초과 프레임 14%)
    p.add_argument("--max-step-deg", type=float, default=20.0, help="한 스텝 최대 관절 이동량 (안전 클리핑, 현재 위치 기준)")
    p.add_argument("--duration", type=float, default=30.0, help="최대 실행 시간(초). 지나면 자동 정지")
    p.add_argument("--start-pose", type=Path, default=DEFAULT_START_POSE)
    p.add_argument("--camera-source", choices=["net", "usbip"], default="net",
                   help="net = Windows 송신기(5558, trial4 녹화와 같음, 11-18 기본), usbip = 예전 방식")
    p.add_argument("--net-camera-port", type=int, default=5558)
    p.add_argument("--log-dir", type=Path, default=Path("/mnt/d/data/flower/policy_runs"),
                   help="실행 기록 저장 위치 (모델이 받은 사진·관절, 매 스텝 명령/잘린 명령/실제 위치, 영상)")
    return p.parse_args()


def main():
    args = parse_args()
    task = TASKS.get(args.task, args.task)

    if args.camera_source == "net":
        camera = NetCamera(port=args.net_camera_port, width=CAM_WIDTH, height=CAM_HEIGHT)
    else:
        camera = UsbipOpenCVCamera(
            OpenCVCameraConfig(
                index_or_path=args.camera, fourcc="MJPG", width=CAM_WIDTH, height=CAM_HEIGHT, fps=30,
                color_mode=ColorMode.RGB,
            )
        )

    # RobotClient.__init__이 make_robot_from_config -> robot.connect()를 바로 호출하므로, 그 사이에 카메라를 끼워 넣는다
    original_make_robot = robot_client.make_robot_from_config

    def make_robot_with_usbip_camera(cfg):
        robot = original_make_robot(cfg)
        robot.cameras = {CAMERA_NAME: camera}  # observation_features(cached)가 계산되기 전이어야 함
        return robot

    robot_client.make_robot_from_config = make_robot_with_usbip_camera

    cfg = RobotClientConfig(
        policy_type="smolvla",
        pretrained_name_or_path=args.model,
        robot=SO101FollowerConfig(
            port=args.robot_port,
            id=ROBOT_ID,
            max_relative_target=args.max_step_deg,
            disable_torque_on_disconnect=False,
        ),
        actions_per_chunk=args.actions_per_chunk,
        task=task,
        server_address=args.server,
        policy_device="cuda",
        chunk_size_threshold=args.chunk_threshold,
        fps=args.fps,
    )

    mjpeg = MjpegServer(port=HTTP_PORT, fps=args.fps)
    client = robot_client.RobotClient(cfg)  # 로봇 + 카메라 연결
    robot = client.robot
    motors = list(robot.bus.motors)
    print(f"task: {task}")
    print(f"서버: {args.server}  모델: {args.model}")
    print(f"카메라 {camera if args.camera_source == 'net' else args.camera}  로봇 {args.robot_port}  fps {args.fps}  시작 자세 {args.start_pose}")
    print(f"미리보기: Windows 브라우저에서 http://localhost:{HTTP_PORT}")

    stop_preview = threading.Event()
    status = {"label": "MOVING TO START"}

    def preview_loop():
        import cv2

        while not stop_preview.is_set():
            try:
                img = camera.read_latest().copy()
                cv2.putText(img, status["label"], (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                mjpeg.update(img)
            except Exception:
                pass
            time.sleep(1 / args.fps)

    threading.Thread(target=preview_loop, daemon=True).start()

    # ----- 시작 자세로 이동 -----
    if args.start_pose.exists():
        goal = json.loads(args.start_pose.read_text())
        obs = robot.get_observation()
        begin = {m: float(obs[f"{m}.pos"]) for m in motors}
        n = max(1, int(max(1.0, max(abs(goal[m] - begin[m]) for m in motors) / MOVE_SPEED) * args.fps))
        for i in range(1, n + int(0.5 * args.fps) + 1):
            a = min(1.0, i / n)
            a = a * a * (3 - 2 * a)
            robot.send_action({f"{m}.pos": begin[m] + a * (goal[m] - begin[m]) for m in motors})
            time.sleep(1 / args.fps)
        print("[시작 자세 도착]")
    else:
        print(f"⚠️ {args.start_pose} 없음 -> 현재 자세에서 시작")

    # ----- 실행 기록 (11-18: 실물이 데이터에 없는 자세로 가서 원인 분석용) -----
    import cv2
    import numpy as np

    run_dir = args.log_dir / f"{time.strftime('%m%d_%H%M%S')}_{args.task if args.task in TASKS else 'custom'}"
    (run_dir / "obs").mkdir(parents=True, exist_ok=True)
    (run_dir / "meta.json").write_text(json.dumps(
        {"task": task, "model": args.model, "start_pose": str(args.start_pose), "fps": args.fps,
         "max_step_deg": args.max_step_deg, "actions_per_chunk": args.actions_per_chunk,
         "chunk_threshold": args.chunk_threshold, "camera_source": args.camera_source}, ensure_ascii=False, indent=1))
    video = cv2.VideoWriter(str(run_dir / "run.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (CAM_WIDTH, CAM_HEIGHT))
    rec = {"t": [], "state": [], "cmd": [], "sent": []}  # 매 스텝 (control 스레드)
    obs_rec = {"t": [], "state": []}  # 모델에 보낸 관측 (사진은 obs/NNN.jpg)
    t_run = time.perf_counter()
    orig_send, orig_obs = robot.send_action, robot.get_observation

    def send_logged(action):
        present = robot.bus.sync_read("Present_Position")  # control 스레드 안이라 버스 충돌 없음
        sent = orig_send(action)
        rec["t"].append(time.perf_counter() - t_run)
        rec["state"].append([present[m] for m in motors])
        rec["cmd"].append([float(action[f"{m}.pos"]) for m in motors])
        rec["sent"].append([float(sent[f"{m}.pos"]) for m in motors])
        try:
            video.write(cv2.cvtColor(camera.read_latest(), cv2.COLOR_RGB2BGR))
        except Exception:
            pass
        return sent

    def obs_logged():
        obs = orig_obs()
        i = len(obs_rec["t"])
        obs_rec["t"].append(time.perf_counter() - t_run)
        obs_rec["state"].append([float(obs[f"{m}.pos"]) for m in motors])
        cv2.imwrite(str(run_dir / "obs" / f"{i:03d}.jpg"), cv2.cvtColor(obs[CAMERA_NAME], cv2.COLOR_RGB2BGR))
        return obs

    robot.send_action, robot.get_observation = send_logged, obs_logged

    # ----- 서버 연결 + 모델 로딩 (서버에서) -----
    status["label"] = "LOADING POLICY"
    print("[서버 연결 / 모델 로딩 중...]")
    if not client.start():
        print("서버 연결 실패. sior에서 serve_policy.py가 떠 있는지, 네트워크(포트 8080) 확인")
        stop_preview.set()
        client.stop()
        return

    receiver = threading.Thread(target=client.receive_actions, daemon=True)
    controller = threading.Thread(target=client.control_loop, kwargs={"task": task}, daemon=True)
    receiver.start()
    controller.start()

    status["label"] = f"RUNNING task {args.task}"
    print(f"[실행 중] 최대 {args.duration:.0f}초   ESC / Space: 정지")

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    t0 = time.perf_counter()
    try:
        tty.setcbreak(fd)
        while controller.is_alive() and time.perf_counter() - t0 < args.duration:
            if select.select([sys.stdin], [], [], 0.05)[0] and sys.stdin.read(1) in ("\x1b", " "):
                print("\n[정지]")
                break
            # 카메라 읽기 스레드가 죽으면(usbip 연결 끊김 등) 관측을 못 보내므로 즉시 정지
            if camera.thread is None or not camera.thread.is_alive():
                print("\n⚠️ 카메라 읽기 중단 -> 정지. Windows에서 `usbipd list`로 카메라가 Attached인지 확인하고 다시 attach")
                break
        else:
            print("\n[시간 종료 -> 정지]")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        client.shutdown_event.set()  # control_loop / receive_actions 멈춤
        controller.join(timeout=2)
        # 현재 위치를 목표로 써서 그 자리에 정지 (토크는 유지). 카메라가 죽어 있을 수 있으니 모터만 직접 읽음
        try:
            present = robot.bus.sync_read("Present_Position")
            robot.bus.sync_write("Goal_Position", present)
        except Exception as e:
            print(f"⚠️ 정지 위치 쓰기 실패: {e}")
        stop_preview.set()
        try:
            client.stop()
        except Exception as e:
            print(f"⚠️ 연결 종료 중 에러 (무시): {e}")
        receiver.join(timeout=2)
        video.release()
        arr = {k: np.array(v, dtype=np.float32) for k, v in rec.items()}
        np.savez(run_dir / "log.npz", **arr, obs_t=np.array(obs_rec["t"], np.float32),
                 obs_state=np.array(obs_rec["state"], np.float32), motors=np.array(motors))
        if len(arr["t"]):
            clipped = np.abs(arr["cmd"] - arr["sent"]) > 0.01
            print(f"[기록] {run_dir}  스텝 {len(arr['t'])}개, 모델 관측 {len(obs_rec['t'])}번, "
                  f"명령이 잘린 스텝 {clipped.any(1).mean():.0%} (관절별 {np.round(clipped.mean(0) * 100).astype(int).tolist()}%)")
            print("   마지막 자세 " + "  ".join(f"{m} {v:.1f}" for m, v in zip(motors, arr["state"][-1])))
        print("종료 (토크 유지 상태 - 팔은 그 자리에 멈춰 있음)")


if __name__ == "__main__":
    main()
