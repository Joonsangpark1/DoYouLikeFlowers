"""
손으로 놓은 위치 vs 로봇이 다시 가는 위치 비교 (재현성 점검).

엔코더 값은 거의 같은데 눈으로 보면 위치가 다르다면 -> 모터 혼 나사 풀림 / 링크 휨 같은 기계 문제.
엔코더 값부터 다르다면 -> 제어(중력 처짐, 게인) 문제.

  1) 토크 OFF 상태에서 팔을 손으로 원하는 위치(예: 꽃 바로 앞)에 두고 Enter -> 엔코더 값 저장, 토크 ON
  2) 그리퍼 끝 위치를 테이프/손가락으로 표시하고 Enter -> 시작 자세로 갔다가 저장한 위치로 복귀
  3) 표시와 비교. 이어서 Enter를 누르면 실시간 값 표시 모드: 토크 ON 상태에서 링크를 살짝 밀어보고
     몸체는 움직이는데 숫자가 안 변하는 관절 = 혼/나사 유격
종료(Ctrl+C) 시 토크는 켠 채로 둔다 (팔 떨어짐 방지).

사용: python repeat_check.py [--robot-port /dev/ttyACM0]
"""
import argparse
import json
import time
from pathlib import Path

from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

ROBOT_ID = "my_follower_arm"
FPS = 20
MOVE_SPEED = 30.0  # deg/s
SETTLE_S = 2.0

p = argparse.ArgumentParser()
p.add_argument("--robot-port", default="/dev/ttyACM0")
args = p.parse_args()

follower = SO101Follower(SO101FollowerConfig(port=args.robot_port, id=ROBOT_ID, disable_torque_on_disconnect=False))
follower.connect()
motors = list(follower.bus.motors)
arm = [m for m in motors if m != "gripper"]
start_pose = json.loads((Path(__file__).parent / "start_pose.json").read_text())


def read_pose() -> dict[str, float]:
    o = follower.get_observation()
    return {m: float(o[f"{m}.pos"]) for m in motors}


def fmt(d: dict[str, float]) -> str:
    return "  ".join(f"{m[:6]} {d[m]:+7.1f}" for m in arm)


def hold_here() -> dict[str, float]:
    pose = read_pose()
    follower.send_action({f"{m}.pos": v for m, v in pose.items()})
    follower.bus.enable_torque()
    return pose


def move_to(pose: dict[str, float]) -> None:
    begin = read_pose()
    dist = max(abs(pose[m] - begin[m]) for m in arm)
    n = max(1, int(max(1.5, dist / MOVE_SPEED) * FPS))
    for i in range(1, n + int(SETTLE_S * FPS) + 1):
        a = min(1.0, i / n)
        a = a * a * (3 - 2 * a)
        follower.send_action({f"{m}.pos": begin[m] + a * (pose[m] - begin[m]) for m in motors})
        time.sleep(1 / FPS)


try:
    hold_here()
    print("[1] 팔을 손으로 받치세요. Enter를 누르면 토크가 꺼집니다 (그리퍼는 유지).")
    input()
    follower.bus.disable_torque(arm)
    print("    원하는 위치로 손으로 옮기고, 받친 채로 Enter")
    input()
    target = read_pose()
    print(f"    저장(엔코더): {fmt(target)}")
    hold_here()
    time.sleep(2.0)
    sag = read_pose()
    print(f"    토크 ON 2초 후 처짐: {fmt({m: sag[m] - target[m] for m in arm})}")

    print("\n[2] 그리퍼 끝 위치를 표시하세요. Enter -> 시작 자세로 갔다가 저장 위치로 복귀")
    input()
    move_to(start_pose)
    move_to(target)
    back = read_pose()
    print(f"    복귀 후 엔코더 오차: {fmt({m: back[m] - target[m] for m in arm})}")
    print("    -> 표시한 위치와 실제로 얼마나 다른지 눈으로 확인 (몇 cm, 어느 방향)")

    print("\n[3] Enter -> 실시간 값 표시. 링크를 하나씩 살짝 밀어보세요. Ctrl+C로 종료")
    input()
    while True:
        cur = read_pose()
        print("\r    " + fmt({m: cur[m] - back[m] for m in arm}), end="", flush=True)
        time.sleep(0.1)
except KeyboardInterrupt:
    print()
finally:
    follower.disconnect()
    print("종료 (토크 유지)")
