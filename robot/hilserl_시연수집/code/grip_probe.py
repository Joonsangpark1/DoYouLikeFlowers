"""그리퍼 값 방향 확인 (11-22): 현재 값 읽기, 인자로 값 주면 그 값으로 천천히 이동. 팔은 그대로.
사용: python grip_probe.py [목표값]"""
import sys, time
from pathlib import Path
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

port = str(sorted(Path("/dev/serial/by-id").glob("usb-1a86_*"))[0].resolve())
r = SO101Follower(SO101FollowerConfig(port=port, id="my_follower_arm", disable_torque_on_disconnect=False))
r.connect(calibrate=False)
cur = r.bus.sync_read("Present_Position")
print("현재", {k: round(v, 1) for k, v in cur.items()})
if len(sys.argv) > 1:
    g0, g1 = cur["gripper"], float(sys.argv[1])
    for i in range(1, 31):
        r.bus.sync_write("Goal_Position", {**cur, "gripper": g0 + i / 30 * (g1 - g0)})
        time.sleep(1 / 30)
    time.sleep(0.5)
    print("이동 후 gripper", round(r.bus.sync_read("Present_Position")["gripper"], 1))
r.disconnect()
