"""보상 분류기용 사진 녹화 (11-23). "통 안에 줄기가 있다(성공) / 아니다" 장면을 고정 카메라(C270)로 모은다.

왜 따로 모으나: HIL prior 시연(record_prior.py)의 성공 사진은 팔이 통을 가려서 '팔 위치'만 보임 → 분류기가
팔 위치로 성공을 판단하게 됨(보상 속이기). 그래서 사용자 결정(11-23):
  A. 성공 = 줄기를 통에 놓고 **팔을 빼서 통이 보이는 상태**. 팔이 통을 가리면 '성공 아님'으로 모음
  B. C270을 팔이 안 가리는 자리로 옮겨 고정

조작 (게임패드, 일반 패드 버튼 번호):
  왼쪽 스틱 앞뒤·좌우 / 오른쪽 스틱 위아래 = 높이, 좌우 = 손목 회전 / R2 닫기 · L2 열기   (teleop과 같음)
  **1을 누르고 있는 동안 = 성공 사진 녹화**   (통 안에 줄기, 통이 보임)
  **3을 누르고 있는 동안 = 실패 사진 녹화**   (빈 통, 가장자리에 걸침, 밖에 떨어짐, 팔이 통을 가림, 잡고 통 위에 있음 등)
  버튼을 떼면 그 구간이 에피소드 1개로 저장 (1초 미만은 버림). SELECT = 종료
  처음엔 ANALOG 확인: 오른쪽 스틱을 한 번 끝까지 밀어야 녹화 버튼이 먹음 (ANALOG 꺼지면 스틱이 버튼 1~4로 들어옴)
  누르고 있는 동안에도 팔·그리퍼를 움직일 수 있음 → 같은 상태를 여러 팔 위치·각도로 담기

저장: LeRobot 데이터셋 (observation.images.front / wrist, observation.state, next.reward = 1 성공 · 0 실패)
미리보기: http://localhost:8080  (위쪽에 상태와 모은 개수)
사용 (WSL, conda activate lerobot, 녹화 송신기 3개 켜 둔 상태):
  python record_reward.py                 # 새로 (저장된 것 있으면 이어서)
"""

from __future__ import annotations

import argparse
import json
import shutil
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np

import lerobot_plugins  # noqa: F401
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot_plugins import BUTTONS, RemoteGamepad, RemoteGamepadConfig
from net_camera import NetCamera
from record_prior import (GREEN, RED, WHITE, YELLOW, _status, by_id, move_smooth, pad_action, read_q, read_volt,
                          set_status, LOW_VOLT, SMOLVLA_CODE)
from usbip_camera import MjpegServer
from wrist_ee import WristEEController

HERE = Path(__file__).resolve().parent
MIN_FRAMES = 10  # 1초 미만 구간은 실수로 보고 버림


def features(state_dim: int, h: int, w: int) -> dict:
    img = {"dtype": "video", "shape": (h, w, 3), "names": ["height", "width", "channels"]}
    return {
        "observation.state": {"dtype": "float32", "shape": (state_dim,), "names": None},
        "observation.images.front": img,
        "observation.images.wrist": dict(img),
        "next.reward": {"dtype": "float32", "shape": (1,), "names": None},
    }


def pressed(pad: RemoteGamepad, name: str) -> bool:
    s = pad._live_state()
    return bool(s is not None and int(s.get("btn", 0)) & BUTTONS[name])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo-id", default=os.environ.get("FLOWER_HF_USER", "parkjoonsang") + "/flower_reward")
    p.add_argument("--fps", type=int, default=10)
    p.add_argument("--config", type=Path, default=HERE / "configs" / "flower_hil.json")
    p.add_argument("--start-pose", type=Path, default=SMOLVLA_CODE / "start_pose_vla_trial4.json")
    p.add_argument("--start-gripper", type=float, default=69.0)
    p.add_argument("--xyz-step", type=float, default=0.008)
    p.add_argument("--roll-step", type=float, default=6.0)
    p.add_argument("--grip-step", type=float, default=10.0)
    args = p.parse_args()

    raw = json.loads(args.config.read_text())
    tcfg, ikcfg = raw["env"]["teleop"], raw["env"]["processor"]["inverse_kinematics"]
    root = Path.home() / "lerobot_data" / args.repo_id
    log_path = root.parent / f"{root.name}_log.jsonl"

    pad = RemoteGamepad(RemoteGamepadConfig(port=tcfg["port"], deadzone=tcfg["deadzone"], always_intervene=True))
    pad.connect()
    front, wrist = NetCamera(port=5559), NetCamera(port=5558)
    front.connect()
    wrist.connect()
    robot = SO101Follower(SO101FollowerConfig(port=by_id("/dev/serial/by-id/usb-1a86_*", "/dev/ttyACM0"),
                                              id="my_follower_arm", disable_torque_on_disconnect=False))
    robot.connect()
    names = list(robot.bus.motors)
    ctrl = WristEEController(str(HERE / ikcfg["urdf_path"]), ikcfg["target_frame_name"], names,
                             xyz_step=args.xyz_step, roll_step=args.roll_step, grip_step=args.grip_step,
                             bounds=ikcfg.get("end_effector_bounds"))

    preview = MjpegServer(port=8080, fps=15)
    stop = threading.Event()

    def preview_loop():
        while not stop.is_set():
            try:
                img = np.hstack([cv2.cvtColor(c.read_latest(1000), cv2.COLOR_RGB2BGR) for c in (front, wrist)])
                cv2.rectangle(img, (0, 0), (img.shape[1], 34), (0, 0, 0), -1)
                cv2.putText(img, _status[0], (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, _status[1], 2)
                preview.update_bgr(img)
            except Exception:
                pass
            time.sleep(1 / 15)

    threading.Thread(target=preview_loop, daemon=True).start()
    print("미리보기: http://localhost:8080  (왼쪽 고정 C270 / 오른쪽 손목)")

    if (root / "meta" / "info.json").exists() and list(root.glob("data/*/*.parquet")):
        dataset = LeRobotDataset.resume(args.repo_id, root=root, image_writer_threads=4)
    else:
        if root.exists():
            shutil.rmtree(root)
        dataset = LeRobotDataset.create(args.repo_id, args.fps, root=root, robot_type="so101_follower", use_videos=True,
                                        image_writer_threads=4, features=features(len(names), front.height, front.width))
    log = [json.loads(l) for l in log_path.read_text().splitlines()] if log_path.exists() else []
    n_pos = sum(r["frames"] for r in log if r["label"] == 1)
    n_neg = sum(r["frames"] for r in log if r["label"] == 0)

    try:
        goal = json.loads(args.start_pose.read_text())
        goal["gripper"] = args.start_gripper
        set_status("MOVING TO START", YELLOW)
        move_smooth(robot, goal, gripper_first=True)
        ctrl.reset_from(read_q(robot, names))
        volt = read_volt(robot)
        print(f"배터리 {volt}V. 오른쪽 스틱을 한 번 끝까지 밀어 ANALOG 확인 → 1(성공)/3(실패)을 누르고 있는 동안 녹화")
        analog_ok, label, frames = False, None, 0
        while True:
            t0 = time.perf_counter()
            if pad.pop_pressed("back"):
                break
            s = pad._live_state() or {}
            if not analog_ok and max(abs(float(s.get("rx", 0))), abs(float(s.get("ry", 0)))) > 0.5:
                analog_ok = True
                print("ANALOG 확인됨")
            want = None
            if analog_ok:
                want = 1 if pressed(pad, "y") else 0 if pressed(pad, "a") else None

            # 팔 조종 (녹화 중에도)
            q = ctrl.step(pad_action(pad, tcfg))
            robot.bus.sync_write("Goal_Position", dict(zip(names, q, strict=True)))

            if want != label:  # 구간 끝 → 저장 또는 버림
                if label is not None:
                    if frames >= MIN_FRAMES:
                        dataset.save_episode()
                        rec = {"episode_index": dataset.num_episodes - 1, "label": label, "frames": frames,
                               "time": time.strftime("%Y-%m-%d %H:%M:%S")}
                        log.append(rec)
                        with log_path.open("a") as f:
                            f.write(json.dumps(rec) + "\n")
                        n_pos, n_neg = (n_pos + frames, n_neg) if label == 1 else (n_pos, n_neg + frames)
                        print(f"  [저장] {'성공' if label == 1 else '실패'} {frames}장  (누적 성공 {n_pos} / 실패 {n_neg})")
                    else:
                        dataset.clear_episode_buffer()
                        print(f"  [버림] {frames}장 (1초 미만)")
                label, frames = want, 0
            if label is not None:
                dataset.add_frame({
                    "observation.state": read_q(robot, names).astype(np.float32),
                    "observation.images.front": front.read_latest(),
                    "observation.images.wrist": wrist.read_latest(),
                    "next.reward": np.array([float(label)], np.float32),
                    "task": "stem in container",
                })
                frames += 1

            if not analog_ok:
                set_status("ANALOG? turn on + move RIGHT stick", YELLOW)
            elif label == 1:
                set_status(f"REC SUCCESS {frames}  (pos {n_pos} / neg {n_neg})", GREEN)
            elif label == 0:
                set_status(f"REC FAIL {frames}  (pos {n_pos} / neg {n_neg})", RED)
            else:
                low = volt is not None and volt < LOW_VOLT
                set_status(f"hold 1=success 3=fail  pos {n_pos} / neg {n_neg}  {volt}V{' LOW' if low else ''}",
                           RED if low else WHITE)
            time.sleep(max(0.0, 1 / args.fps - (time.perf_counter() - t0)))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            dataset.clear_episode_buffer()
        except Exception:
            pass
        dataset.finalize()
        stop.set()
        cur = robot.bus.sync_read("Present_Position")
        robot.bus.sync_write("Goal_Position", cur)
        robot.disconnect()
        pad.disconnect()
        front.disconnect()
        wrist.disconnect()
        print(f"종료. {root}  에피소드 {dataset.num_episodes}개, 성공 {n_pos}장 / 실패 {n_neg}장")


if __name__ == "__main__":
    main()
