"""하드웨어 점검 (11-22): 모터 전압·온도 + 손목 카메라(5558) 프레임 속도."""
import time
from pathlib import Path

from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

from net_camera import NetCamera

port = str(sorted(Path("/dev/serial/by-id").glob("usb-1a86_*"))[0].resolve())
robot = SO101Follower(SO101FollowerConfig(port=port, id="my_follower_arm", disable_torque_on_disconnect=False))
robot.connect(calibrate=False)
for m in robot.bus.motors:
    v = robot.bus.read("Present_Voltage", m, normalize=False) / 10
    t = robot.bus.read("Present_Temperature", m, normalize=False)
    print(f"{m:14s} {v:4.1f} V  {t} °C")
robot.disconnect()

cam = NetCamera(port=5558, width=640, height=480)
cam.connect()
n, t0, last = 0, time.time(), None
while time.time() - t0 < 5:
    img = cam.read_latest(max_age_ms=1000)
    if last is None or img is not last:
        n += 1
        last = img
    time.sleep(0.005)
print(f"손목 카메라 5초: {n}장 ({n / 5:.1f} fps)")
cam.disconnect()
