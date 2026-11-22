"""현재 관절 6개를 쉼표로 출력 (토크 안 건드림, 11-22)."""
from pathlib import Path
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

port = str(sorted(Path("/dev/serial/by-id").glob("usb-1a86_*"))[0].resolve())
r = SO101Follower(SO101FollowerConfig(port=port, id="my_follower_arm", disable_torque_on_disconnect=False))
r.bus.connect()
print(",".join(str(round(v, 1)) for v in r.bus.sync_read("Present_Position").values()))
r.bus.disconnect(disable_torque=False)
