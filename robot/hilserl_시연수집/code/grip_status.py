"""그리퍼 상태 (11-22 재조립 확인): 캘리브레이션 파일 값, 원시 위치, 정규화 값, 토크."""
import json
from pathlib import Path
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

port = str(sorted(Path("/dev/serial/by-id").glob("usb-1a86_*"))[0].resolve())
r = SO101Follower(SO101FollowerConfig(port=port, id="my_follower_arm", disable_torque_on_disconnect=False))
print("캘리브레이션 파일", r.calibration_fpath, "수정", __import__("time").ctime(r.calibration_fpath.stat().st_mtime))
print("gripper 캘리브레이션", r.calibration["gripper"])
r.connect(calibrate=False)
raw = r.bus.read("Present_Position", "gripper", normalize=False)
print("원시", raw, " 정규화", round(r.bus.read("Present_Position", "gripper"), 1),
      " 토크", r.bus.read("Torque_Enable", "gripper"), " 모터 Homing_Offset", r.bus.read("Homing_Offset", "gripper", normalize=False))
r.disconnect()
