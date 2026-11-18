"""그리퍼만 다시 캘리브레이션한 결과를 팀 공통 파일에 병합 (팔 관절 5개는 그대로 → 기존 데이터와 관절 기준 유지).

순서:
  1) lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/ttyACM0 --robot.id=gripper_tmp
     (임시 id라 공통 파일 my_follower_arm.json은 안 건드림)
  2) python merge_gripper_calib.py            # 확인만 (바뀌는 값 출력)
     python merge_gripper_calib.py --write    # 공통 파일 + 설치된 사본 + hilserl 폴더 사본 갱신
  3) 다음 연결 때 lerobot이 "provided calibration file" 쓸지 물으면 ENTER (병합된 값이 모터에 기록됨)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEAM = HERE / "calibration" / "my_follower_arm.json"
HILSERL = HERE.parent.parent / "hilserl_시연수집" / "code" / "calibration" / "my_follower_arm.json"
CALIB_DIR = Path(os.environ.get("HF_LEROBOT_CALIBRATION",
                                Path(os.environ.get("HF_LEROBOT_HOME", Path.home() / ".cache/huggingface/lerobot"))
                                / "calibration")) / "robots" / "so_follower"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tmp-id", default="gripper_tmp")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    new = json.loads((CALIB_DIR / f"{args.tmp_id}.json").read_text())
    team = json.loads(TEAM.read_text())
    g_old, g_new = team["gripper"], new["gripper"]
    print("gripper 기존:", g_old)
    print("gripper 새값:", g_new)
    span_old, span_new = g_old["range_max"] - g_old["range_min"], g_new["range_max"] - g_new["range_min"]
    print(f"범위 폭 {span_old} → {span_new} (모터 단위, 4096 = 1바퀴)")
    for k in team:
        if k != "gripper" and team[k] != new[k]:
            print(f"  (참고) {k}: 임시 캘리브레이션 값이 다름 — 병합 안 함, 기존 유지")

    if not args.write:
        print("\n--write 를 붙이면 반영합니다.")
        return
    team["gripper"] = g_new
    text = json.dumps(team, indent=4)
    TEAM.write_text(text)
    print("갱신:", TEAM)
    if HILSERL.exists():
        HILSERL.write_text(text)
        print("갱신:", HILSERL)
    CALIB_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(TEAM, CALIB_DIR / "my_follower_arm.json")
    print("설치:", CALIB_DIR / "my_follower_arm.json")


if __name__ == "__main__":
    main()
