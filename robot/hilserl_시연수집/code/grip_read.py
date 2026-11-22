"""그리퍼 값만 읽기 (토크 안 건드림, 11-22). robot.connect()는 configure에서 토크를 켜서 bus만 연결."""
from pathlib import Path
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

port = str(sorted(Path("/dev/serial/by-id").glob("usb-1a86_*"))[0].resolve())
r = SO101Follower(SO101FollowerConfig(port=port, id="my_follower_arm", disable_torque_on_disconnect=False))
r.bus.connect()
print("gripper 원시", r.bus.read("Present_Position", "gripper", normalize=False),
      " 정규화", round(r.bus.read("Present_Position", "gripper"), 1), " 토크", r.bus.read("Torque_Enable", "gripper"))
r.bus.disconnect(disable_torque=False)
