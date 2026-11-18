"""
관절 몇 개만 캘리브레이션을 다시 잡는 도구. lerobot-calibrate 전체를 다시 할 필요 없음.

언제 쓰나:
  - lerobot-calibrate 결과에서 어떤 관절 범위가 360도(예: 2~4087)로 나왔을 때
    ("가운데 자세"에서 Enter를 누를 때 그 관절이 한쪽 끝에 있어서 숫자가 4095->0으로 넘어간 것)
  - 그리퍼 패드를 바꿔서 그리퍼가 닫히는 끝 위치가 달라졌을 때 (--motors gripper)

가운데 자세를 맞출 필요가 없다. 관절을 끝에서 끝까지 움직이기만 하면, 그 범위의 가운데가
2047(= 0도)이 되도록 기준(Homing_Offset)과 범위를 계산해서 파일과 모터에 같이 쓴다.
(lerobot은 각도를 '범위 가운데 = 0도'로 계산하므로, 결과는 정상 캘리브레이션과 같다)

사용 (Ubuntu, conda activate lerobot, 다른 로봇 프로그램은 끈 상태):
  python recenter_calibration.py --motors wrist_flex shoulder_lift
  python recenter_calibration.py --motors gripper
"""
import argparse
import select
import sys
import time

from lerobot.motors import MotorCalibration
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

ROBOT_ID = "my_follower_arm"
CENTER = 2047
RES = 4096


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--motors", nargs="+", required=True)
    p.add_argument("--port", default="/dev/ttyACM0")
    args = p.parse_args()

    robot = SO101Follower(SO101FollowerConfig(port=args.port, id=ROBOT_ID))
    if not robot.calibration:
        sys.exit(f"캘리브레이션 파일이 없습니다: {robot.calibration_fpath} (lerobot-calibrate를 먼저 한 번 하세요)")
    bad = [m for m in args.motors if m not in robot.bus.motors or m == "wrist_roll"]
    if bad:
        sys.exit(f"잘못된 모터 이름: {bad} (wrist_roll은 한 바퀴 관절이라 대상 아님)")

    robot.bus.connect()
    robot.bus.disable_torque(args.motors)
    print(f"{args.motors} 힘을 뺐습니다. 팔을 손으로 받치세요.")
    print("각 관절을 막힐 때까지 양쪽 끝으로 천천히 움직이세요. 다 했으면 Enter.\n")

    prev = robot.bus.sync_read("Present_Position", args.motors, normalize=False)
    unwrapped = {m: float(v) for m, v in prev.items()}
    lo = dict(unwrapped)
    hi = dict(unwrapped)
    while not select.select([sys.stdin], [], [], 0)[0]:
        cur = robot.bus.sync_read("Present_Position", args.motors, normalize=False)
        for m in args.motors:
            d = cur[m] - prev[m]
            if d > RES / 2:  # 0 -> 4095 로 넘어감
                d -= RES
            elif d < -RES / 2:  # 4095 -> 0 으로 넘어감
                d += RES
            unwrapped[m] += d
            lo[m] = min(lo[m], unwrapped[m])
            hi[m] = max(hi[m], unwrapped[m])
        prev = cur
        line = "  ".join(f"{m}: {(hi[m] - lo[m]) * 360 / RES:5.1f}도" for m in args.motors)
        print(f"\r범위 {line}   ", end="", flush=True)
        time.sleep(0.02)
    sys.stdin.readline()
    print()

    for m in args.motors:
        span = hi[m] - lo[m]
        old = robot.calibration[m]
        shift = round((lo[m] + hi[m]) / 2 - CENTER)
        new_offset = ((old.homing_offset + shift + RES // 2) % RES) - RES // 2  # -2048~2047 로
        new_min, new_max = int(round(lo[m] - shift)), int(round(hi[m] - shift))
        print(f"{m:14s} 범위 {span * 360 / RES:5.1f}도 | 기준 {old.homing_offset} -> {new_offset}, "
              f"범위 {old.range_min}~{old.range_max} -> {new_min}~{new_max}")
        if span * 360 / RES < 60:
            sys.exit(f"  {m} 움직인 범위가 너무 작습니다. 저장하지 않고 종료합니다.")
        if not (0 <= new_min and new_max <= RES - 1) or abs(new_offset) > 2047:
            sys.exit("  범위가 한 바퀴를 넘습니다. 저장하지 않고 종료합니다.")
        robot.calibration[m] = MotorCalibration(
            id=old.id, drive_mode=old.drive_mode, homing_offset=new_offset, range_min=new_min, range_max=new_max
        )

    robot.bus.write_calibration(robot.calibration)
    robot._save_calibration()
    robot.bus.disconnect(disable_torque=True)
    print(f"\n저장 완료: {robot.calibration_fpath} (모터에도 기록함)")


if __name__ == "__main__":
    main()
