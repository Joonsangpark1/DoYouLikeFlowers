"""
HIL-SERL 녹화 전에 1번: 작업 영역(EE bounds)과 시작 자세(reset pose)를 손으로 직접 재서 config에 써 넣는다.

HIL-SERL은 로봇 끝단(EE)을 정해진 상자 안에서만 움직이게 한다 (end_effector_bounds).
상자가 너무 크면 학습이 느리고 위험하고, 너무 작으면 작업을 못 한다. 그래서 "작업에 필요한 공간"을
손으로 직접 훑어서 잰다. (공식 lerobot-find-joint-limits는 리더 암이 필요해서 따로 만듦)

순서:
  1) 실행하면 3초 카운트다운 뒤 모터 힘이 빠짐 (⚠️ 팔을 손으로 받치기)
  2) 작업에 필요한 범위를 손으로 천천히 다 훑기 (꽃 잡는 위치, 꽂는 위치, 그 사이 경로)
  3) 에피소드 시작 자세에 팔을 두고 Enter -> 시작 자세로 기록 (그리퍼도 원하는 상태로)
  4) q -> 힘 다시 들어감, 결과 출력 + config에 저장 (--no-write면 출력만)

사용:
  python measure_workspace.py                         # configs/flower_hil.json 갱신
  python measure_workspace.py --config configs/다른.json --margin 0.01
"""
from __future__ import annotations

import argparse
import json
import select
import shutil
import sys
import termios
import time
import tty
from pathlib import Path

import numpy as np

from lerobot.model import RobotKinematics
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

HERE = Path(__file__).resolve().parent
COUNTDOWN_S = 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=HERE / "configs" / "flower_hil.json")
    parser.add_argument("--margin", type=float, default=0.01, help="잰 범위 바깥으로 이만큼(m) 여유를 줌")
    parser.add_argument("--no-write", action="store_true", help="config를 고치지 않고 출력만")
    args = parser.parse_args()

    cfg = json.loads(args.config.read_text())
    robot_cfg = cfg["env"]["robot"]
    ik_cfg = cfg["env"]["processor"]["inverse_kinematics"]
    urdf = Path(ik_cfg["urdf_path"])
    if not urdf.is_absolute():
        urdf = HERE / urdf

    robot = SO101Follower(SO101FollowerConfig(port=robot_cfg["port"], id=robot_cfg["id"]))
    robot.connect()
    motors = list(robot.bus.motors)
    kin = RobotKinematics(str(urdf), ik_cfg["target_frame_name"], joint_names=motors)

    def read_q() -> np.ndarray:
        o = robot.get_observation()
        return np.array([o[f"{m}.pos"] for m in motors], dtype=float)

    def hold_here() -> None:
        q = read_q()
        robot.send_action({f"{m}.pos": float(v) for m, v in zip(motors, q, strict=True)})
        robot.bus.enable_torque()

    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    reset_pose: list[float] | None = None

    print(f"\n⚠️ {COUNTDOWN_S}초 뒤 모터 힘이 빠집니다. 팔을 손으로 받치세요.")
    for s in range(COUNTDOWN_S, 0, -1):
        print(f"   {s}...")
        time.sleep(1)
    robot.bus.disable_torque()
    print("\n작업 범위를 손으로 천천히 훑으세요.  Enter: 현재 자세를 시작 자세로   q: 끝\n")

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        done = False
        while not done:
            q = read_q()
            pos = kin.forward_kinematics(q)[:3, 3]
            lo, hi = np.minimum(lo, pos), np.maximum(hi, pos)
            print(
                f"\r EE x={pos[0]:+.3f} y={pos[1]:+.3f} z={pos[2]:+.3f} m   "
                f"범위 x[{lo[0]:+.3f},{hi[0]:+.3f}] y[{lo[1]:+.3f},{hi[1]:+.3f}] z[{lo[2]:+.3f},{hi[2]:+.3f}]  ",
                end="",
                flush=True,
            )
            while select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.read(1)
                if ch in ("\n", "\r"):
                    reset_pose = [round(float(v), 2) for v in q]
                    print("\n[시작 자세 기록] " + ", ".join(f"{m}={v:.1f}" for m, v in zip(motors, reset_pose, strict=True)))
                elif ch.lower() == "q" or ch == "\x1b":
                    done = True
            time.sleep(0.05)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        hold_here()  # 힘 다시 넣기 (현재 자세 유지)
        robot.config.disable_torque_on_disconnect = False
        robot.disconnect()

    if not np.isfinite(lo).all():
        print("\n측정값 없음")
        return
    bounds = {
        "min": [round(float(v), 3) for v in lo - args.margin],
        "max": [round(float(v), 3) for v in hi + args.margin],
    }
    print("\n\n결과")
    print(f"  end_effector_bounds (여유 {args.margin} m 포함): {bounds}")
    if reset_pose is None:
        print("  시작 자세: 기록 안 함 (Enter를 안 누름) -> config의 기존 값 유지")
    else:
        # 시작 자세도 훑는 도중에 잰 값이라 항상 범위 안에 들어 있음 (밖이면 첫 스텝에 EE가 범위로 튀어 들어감)
        print(f"  fixed_reset_joint_positions: {reset_pose}  (순서: {motors})")

    if args.no_write:
        return
    shutil.copy(args.config, args.config.with_suffix(".json.bak"))
    ik_cfg["end_effector_bounds"] = bounds
    if reset_pose is not None:
        cfg["env"]["processor"]["reset"]["fixed_reset_joint_positions"] = reset_pose
    args.config.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{args.config} 에 저장 (이전 파일: {args.config.with_suffix('.json.bak').name})")


if __name__ == "__main__":
    main()
