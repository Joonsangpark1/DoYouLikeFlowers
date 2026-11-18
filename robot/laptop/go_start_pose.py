"""로봇을 시작 자세(trial3 녹화 때 쓴 start_pose.json)로 천천히 이동만 한다. 모델 실행 없음.

사용: python go_start_pose.py [--start-pose 경로] [--speed 30]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

from run_remote_policy import DEFAULT_START_POSE, ROBOT_ID, ROBOT_PORT, _by_id


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start-pose", type=Path, default=DEFAULT_START_POSE)
    p.add_argument("--speed", type=float, default=30.0, help="가장 많이 움직이는 관절 기준 deg/s")
    p.add_argument("--robot-port", default=_by_id("/dev/serial/by-id/usb-1a86_*", ROBOT_PORT))
    args = p.parse_args()

    goal = json.loads(args.start_pose.read_text())
    robot = SO101Follower(SO101FollowerConfig(port=args.robot_port, id=ROBOT_ID, disable_torque_on_disconnect=False))
    robot.connect()
    try:
        motors = list(robot.bus.motors)
        obs = robot.get_observation()
        begin = {m: float(obs[f"{m}.pos"]) for m in motors}
        far = max(abs(goal[m] - begin[m]) for m in motors)
        print(f"시작 자세로 이동: 가장 먼 관절 {far:.0f}° ({far / args.speed:.1f}초)", flush=True)
        hz = 30
        n = max(1, int(far / args.speed * hz))
        for i in range(1, n + hz // 2 + 1):
            a = min(1.0, i / n)
            a = a * a * (3 - 2 * a)
            robot.send_action({f"{m}.pos": begin[m] + a * (goal[m] - begin[m]) for m in motors})
            time.sleep(1 / hz)
        obs = robot.get_observation()
        err = max(abs(goal[m] - float(obs[f"{m}.pos"])) for m in motors)
        print(f"[시작 자세 도착] 남은 차이 최대 {err:.1f}°", flush=True)
    finally:
        robot.disconnect()


if __name__ == "__main__":
    main()
