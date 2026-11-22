"""VLA 시작 자세 후보 캡처 (11-22). 시작 화면에서 세 꽃이 겹치지 않고 다 보이는 자세를 찾기 위함.

동작:
  1. 로봇이 지금 VLA 시작 자세(start_pose_vla_trial4.json)로 천천히 이동 → 후보 0
  2. F: 팔 토크 끄기 (손으로 옮김, 그리퍼는 유지)   H: 지금 자리에서 토크 켜고 고정
     Enter: 손목 카메라 사진 + 관절값 저장           Z: VLA 시작 자세로 다시 이동   Q: 끝 (토크 유지)
  미리보기 http://localhost:8080 에 꽃 색 면적(%)이 실시간으로 뜸 (rose/blue/sunflower, 화면 비율).
  분홍 테이프 같은 같은 색 물건도 잡히니 시야에서 치우고 볼 것.

저장: /mnt/d/data/flower/start_pose_candidates/MMDD_HHMMSS_NN.jpg + .json (관절값, 면적)

사용 (WSL, conda activate lerobot, Windows camera_sender_windows.py --find innomaker 켜둔 상태):
  python capture_start.py
"""

from __future__ import annotations

import json
import select
import sys
import termios
import time
import tty
from pathlib import Path

import cv2
import numpy as np
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

from net_camera import NetCamera
from usbip_camera import MjpegServer

HERE = Path(__file__).resolve().parent
START_POSE = HERE / "start_pose_vla_trial4.json"
OUT_DIR = Path("/mnt/d/data/flower/start_pose_candidates")
ROBOT_ID = "my_follower_arm"
GRIPPER = "gripper"
FPS = 10
MOVE_SPEED = 20.0  # 도/초


def by_id(pattern: str, default: str) -> str:
    hits = sorted(Path("/dev/serial/by-id").glob(pattern)) if Path("/dev/serial/by-id").exists() else []
    return str(hits[0].resolve()) if hits else default


def flower_masks(rgb: np.ndarray) -> dict[str, np.ndarray]:
    """vis.py(11-22 시작 화면 가시성 측정)와 같은 HSV 범위."""
    h = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H, S, V = h[..., 0].astype(int), h[..., 1].astype(int), h[..., 2].astype(int)
    return {
        "rose": ((H >= 160) | (H <= 8)) & (S >= 60) & (V >= 120),
        "blue": (H >= 95) & (H <= 125) & (S >= 60) & (V >= 90),
        "sunflower": (H >= 15) & (H <= 35) & (S >= 110) & (V >= 140),
    }


def areas(rgb: np.ndarray) -> dict[str, float]:
    return {k: float(m.mean() * 100) for k, m in flower_masks(rgb).items()}


def read_keys() -> list[str]:
    keys = []
    while select.select([sys.stdin], [], [], 0)[0]:
        keys.append(sys.stdin.read(1))
    return keys


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    camera = NetCamera(port=5558, width=640, height=480)
    robot = SO101Follower(SO101FollowerConfig(port=by_id("usb-1a86_*", "/dev/ttyACM0"), id=ROBOT_ID))
    mjpeg = MjpegServer(port=8080, fps=FPS)
    camera.connect()
    robot.connect()
    motors = list(robot.bus.motors)
    arm = [m for m in motors if m != GRIPPER]

    def read_pose() -> dict[str, float]:
        o = robot.get_observation()
        return {m: float(o[f"{m}.pos"]) for m in motors}

    def preview(label: str) -> np.ndarray:
        img = camera.read_latest(max_age_ms=1000)
        a = areas(img)
        p = img.copy()
        overlay = p.copy()
        for name, color in (("rose", (255, 0, 255)), ("blue", (0, 90, 255)), ("sunflower", (255, 220, 0))):
            overlay[flower_masks(img)[name]] = color
        p = cv2.addWeighted(overlay, 0.35, p, 0.65, 0)
        cv2.putText(p, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        cv2.putText(p, f"rose {a['rose']:.1f}%  blue {a['blue']:.1f}%  sun {a['sunflower']:.1f}%",
                    (10, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        mjpeg.update(p)
        return img

    def move_to(pose: dict[str, float]) -> None:
        begin = read_pose()
        dist = max(abs(pose[m] - begin[m]) for m in motors if m in pose)
        n = max(1, int(max(1.0, dist / MOVE_SPEED) * FPS))
        for i in range(1, n + int(0.5 * FPS) + 1):
            a = min(1.0, i / n)
            robot.send_action({f"{m}.pos": begin[m] + a * (pose.get(m, begin[m]) - begin[m]) for m in motors})
            preview("MOVING")
            time.sleep(1.0 / FPS)

    def hold_here() -> None:
        pose = read_pose()
        robot.send_action({f"{m}.pos": v for m, v in pose.items()})
        robot.bus.enable_torque()

    start = json.loads(START_POSE.read_text())
    print(f"VLA 시작 자세로 이동: {start}")
    move_to(start)
    print("미리보기: Windows 브라우저 http://localhost:8080")
    print("F 토크 끄기(손으로 옮김)  H 여기서 고정  Enter 저장  Z 시작 자세로  Q 끝")

    old = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    n_saved, free = 0, False
    try:
        while True:
            img = preview("FREE (move by hand)" if free else "HOLD")
            for k in read_keys():
                k = k.lower()
                if k == "f":
                    robot.bus.disable_torque(arm)
                    free = True
                    print("[토크 끔] 손으로 팔을 옮기세요. H로 고정")
                elif k == "h":
                    hold_here()
                    free = False
                    print("[고정]")
                elif k == "z":
                    hold_here()
                    free = False
                    move_to(start)
                    print("[VLA 시작 자세]")
                elif k in ("\n", "\r"):
                    pose, a = read_pose(), areas(img)
                    stem = f"{time.strftime('%m%d_%H%M%S')}_{n_saved:02d}"
                    cv2.imwrite(str(OUT_DIR / f"{stem}.jpg"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
                    (OUT_DIR / f"{stem}.json").write_text(json.dumps({"pose": pose, "area_pct": a}, indent=1))
                    print(f"[저장 {n_saved}] {stem}  " + " ".join(f"{m[:5]}={v:.1f}" for m, v in pose.items())
                          + f"  | rose {a['rose']:.1f}% blue {a['blue']:.1f}% sun {a['sunflower']:.1f}%")
                    n_saved += 1
                elif k == "q":
                    raise KeyboardInterrupt
            time.sleep(1.0 / FPS)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        hold_here()  # 끝낼 때 팔이 떨어지지 않게 지금 자리에서 토크 유지
        camera.disconnect()
        print(f"끝. 저장 {n_saved}장 → {OUT_DIR}")


if __name__ == "__main__":
    main()
