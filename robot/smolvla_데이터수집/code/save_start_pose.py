"""
시작 자세를 손으로 잡아서 저장하는 도구.

모터 힘을 빼고 -> 팔을 손으로 원하는 자세에 놓고 -> Enter 를 누르면 그 자세를 start_pose.json 에 저장하고
그 자리에서 다시 힘을 넣어 멈춘다. (record_dataset.py 의 O 키와 같은 파일에 같은 형식으로 저장)

자세를 잡는 동안 카메라 화면을 Windows 브라우저 http://localhost:8080 에서 볼 수 있다.

사용 (Ubuntu, conda activate lerobot, 녹화 프로그램은 끈 상태):
  python save_start_pose.py
  python save_start_pose.py --camera /dev/video2      # 카메라 번호가 다를 때
  python save_start_pose.py --no-camera               # 카메라 없이
"""
import argparse
import json
import threading
import time
from pathlib import Path

from lerobot.cameras import ColorMode
from lerobot.cameras.opencv import OpenCVCameraConfig
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

from usbip_camera import MjpegServer, UsbipOpenCVCamera

ROBOT_ID = "my_follower_arm"
START_POSE = Path(__file__).parent / "start_pose.json"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--camera", default="/dev/video0")
    p.add_argument("--no-camera", action="store_true")
    args = p.parse_args()

    stop = threading.Event()
    camera = None
    if not args.no_camera:
        camera = UsbipOpenCVCamera(OpenCVCameraConfig(
            index_or_path=args.camera, fourcc="MJPG", width=640, height=480, fps=30, color_mode=ColorMode.RGB))
        mjpeg = MjpegServer(port=8080, fps=15)
        camera.connect()

        def preview_loop():
            while not stop.is_set():
                try:
                    mjpeg.update(camera.read())
                except Exception:
                    time.sleep(0.1)

        threading.Thread(target=preview_loop, daemon=True).start()
        print("카메라 미리보기: Windows 브라우저에서 http://localhost:8080")

    robot = SO101Follower(SO101FollowerConfig(port=args.port, id=ROBOT_ID, disable_torque_on_disconnect=False))
    robot.connect()
    motors = list(robot.bus.motors)

    for i in range(3, 0, -1):
        print(f"\r{i}초 뒤 힘이 빠집니다 - 팔을 손으로 받치세요!   ", end="", flush=True)
        time.sleep(1)
    robot.bus.disable_torque()
    print("\n[힘 뺌] 손으로 팔을 시작 자세에 놓고, 받친 채로 Enter")
    input()

    obs = robot.get_observation()
    pose = {m: round(float(obs[f"{m}.pos"]), 2) for m in motors}
    robot.send_action({f"{m}.pos": v for m, v in pose.items()})  # 목표를 현재 위치로 써두고 힘 넣기 (튀지 않게)
    robot.bus.enable_torque()

    if START_POSE.exists():
        START_POSE.replace(START_POSE.with_suffix(".json.bak"))
    START_POSE.write_text(json.dumps(pose, indent=2))
    print("[저장] " + ", ".join(f"{m}={v:.1f}" for m, v in pose.items()))
    print(f"-> {START_POSE}  (힘 들어간 채로 멈춤. 이전 파일은 .json.bak)")
    robot.disconnect()
    stop.set()
    if camera is not None:
        camera.disconnect()


if __name__ == "__main__":
    main()
