"""모터 전압·온도만 읽기 (토크 안 건드림, 11-22)."""
from pathlib import Path
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

port = str(sorted(Path("/dev/serial/by-id").glob("usb-1a86_*"))[0].resolve())
r = SO101Follower(SO101FollowerConfig(port=port, id="my_follower_arm", disable_torque_on_disconnect=False))
r.bus.connect()
for m in r.bus.motors:
    v = r.bus.read("Present_Voltage", m, normalize=False) / 10
    t = r.bus.read("Present_Temperature", m, normalize=False)
    print(f"{m:14s} {v:4.1f} V  {t} °C")
r.bus.disconnect(disable_torque=False)
