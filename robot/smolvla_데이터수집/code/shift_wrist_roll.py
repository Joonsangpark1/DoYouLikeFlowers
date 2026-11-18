"""wrist_roll 캘리브레이션 기준점을 180°(2048) 옮긴다 (11-17, trial4부터).

왜: 손목 회전 작업 자세가 ±180° 경계(−179° / +179°)에 붙어 있어서, 시연 중 1~2°만 넘어가도 값이 반대 부호로
뒤집히고, 시작 자세로 갈 때 손목이 반대 방향으로 거의 한 바퀴 돎. 기준점을 180° 옮기면 같은 자세가 약 0°로 읽힘.
(recenter_calibration.py는 wrist_roll을 막아 둠 — 범위가 0~4095 전체라 범위 가운데 계산이 안 맞음)

파일(~/.cache/.../my_follower_arm.json)과 모터 둘 다에 쓴다. 팀 공통 파일 동기화는 따로.
사용 (Ubuntu, 다른 로봇 프로그램 끈 상태): python shift_wrist_roll.py [--port /dev/ttyACM0]
"""
import argparse

from lerobot.motors import MotorCalibration
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

RES = 4096

p = argparse.ArgumentParser()
p.add_argument("--port", default="/dev/ttyACM0")
args = p.parse_args()

robot = SO101Follower(SO101FollowerConfig(port=args.port, id="my_follower_arm", disable_torque_on_disconnect=False))
robot.connect(calibrate=False)
try:
    before = float(robot.get_observation()["wrist_roll.pos"])
    old = robot.calibration["wrist_roll"]
    new_offset = ((old.homing_offset + RES // 2 + RES // 2) % RES) - RES // 2  # -2048~2047
    robot.calibration["wrist_roll"] = MotorCalibration(
        id=old.id, drive_mode=old.drive_mode, homing_offset=new_offset, range_min=old.range_min, range_max=old.range_max)
    # 손목 회전 모터의 Homing_Offset만 씀 (write_calibration은 모든 모터에 써서 다른 관절 힘을 빼야 할 수 있음)
    robot.bus.disable_torque(["wrist_roll"])
    robot.bus.write("Homing_Offset", "wrist_roll", new_offset, normalize=False)
    robot.bus.calibration = robot.calibration
    robot.bus.enable_torque(["wrist_roll"])
    robot._save_calibration()
    after = float(robot.get_observation()["wrist_roll.pos"])
    robot.bus.write("Goal_Position", "wrist_roll", after)   # 지금 자리를 목표로 (안 움직이게)
    print(f"wrist_roll homing_offset {old.homing_offset} -> {new_offset}")
    print(f"읽은 값 {before:+.1f}° -> {after:+.1f}° (차이 {((after - before + 180) % 360) - 180:+.1f}°, 기대 ±180)")
    print(f"저장: {robot.calibration_fpath}")
finally:
    robot.disconnect()
