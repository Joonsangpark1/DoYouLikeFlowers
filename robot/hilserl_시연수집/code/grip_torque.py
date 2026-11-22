"""그리퍼 모터만 토크 끄기/켜기 (11-22 그리퍼 재조립용). 사용: python grip_torque.py off|on"""
import sys
from pathlib import Path
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

port = str(sorted(Path("/dev/serial/by-id").glob("usb-1a86_*"))[0].resolve())
r = SO101Follower(SO101FollowerConfig(port=port, id="my_follower_arm", disable_torque_on_disconnect=False))
r.connect(calibrate=False)
if sys.argv[1] == "off":
    r.bus.disable_torque("gripper")
else:
    g = r.bus.sync_read("Present_Position")["gripper"]
    r.bus.sync_write("Goal_Position", {"gripper": g})
    r.bus.enable_torque("gripper")
print("gripper 토크", sys.argv[1], " 현재값", round(r.bus.sync_read("Present_Position")["gripper"], 1))
r.disconnect()
