"""
게임패드가 제대로 들어오는지 로봇 없이 확인한다. (Windows에서 gamepad_sender.ps1을 켜 둔 상태로 실행)

화면에 녹화 때 실제로 기록될 값이 그대로 나온다:
  dx dy dz   : -1 ~ 1 (스틱 기울기). 로봇에서는 x 스텝 크기(m)를 곱해서 끝단(EE)을 움직임
  gripper    : 0 닫기 / 1 유지 / 2 열기
  RB         : 개입 버튼 (시연 녹화 때는 안 눌러도 됨)
  버튼 이벤트: Y 성공 / A 실패 / X 다시 찍기 / Start / Back

사용:
  python gamepad_test.py                        # configs/flower_hil.json의 teleop 설정 사용
  python gamepad_test.py --config configs/다른설정.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from lerobot_plugins import BUTTONS, RemoteGamepad, RemoteGamepadConfig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "configs" / "flower_hil.json")
    args = parser.parse_args()

    teleop_cfg = json.loads(args.config.read_text())["env"]["teleop"]
    teleop_cfg.pop("type", None)
    pad = RemoteGamepad(RemoteGamepadConfig(**teleop_cfg))
    pad.connect()

    print("\n스틱/버튼을 움직여 보세요. Ctrl+C 종료\n")
    print("확인할 것 (로봇 기준 방향은 실제 로봇에서 한 번 더 확인):")
    print("  왼쪽 스틱 위 -> dx +   왼쪽 스틱 왼쪽 -> dy +   오른쪽 스틱 위 -> dz +")
    print("  RT 누름 -> gripper 0(닫기)   LT 누름 -> gripper 2(열기)\n")
    try:
        while True:
            a = pad.get_action()
            s = pad._live_state()
            rb = s is not None and bool(int(s.get("btn", 0)) & BUTTONS["rb"])
            events = [name.upper() for name in ("y", "a", "x", "start", "back") if pad.pop_pressed(name)]
            line = (
                f"\r{'연결OK' if s else '입력없음'}  dx={a['delta_x']:+.2f} dy={a['delta_y']:+.2f} "
                f"dz={a['delta_z']:+.2f}  gripper={int(a.get('gripper', 1))}  RB={'ON ' if rb else 'off'}"
            )
            print(line + "   ", end="", flush=True)
            if events:
                print(f"\n  -> 버튼: {' '.join(events)}")
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        pad.disconnect()
        print()


if __name__ == "__main__":
    main()
