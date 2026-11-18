"""
녹화 없이 게임패드로 로봇만 움직여 본다. (Windows에서 gamepad_sender.ps1을 켜 둔 상태로 실행)

record_demos.py와 같은 부품(make_robot_env / make_processors / step_env_and_process_transition)을 쓰므로
스틱 -> 끝단 이동 -> IK -> 관절 명령 경로가 녹화 때와 똑같다. 다른 점:
  - 카메라 안 씀, 데이터셋 안 만듦
  - 시작 자세로 이동하지 않음 (지금 자세에서 바로 시작)
  - 작업 영역 상자: config에 없으면 지금 끝단 위치 ±margin (기본 6cm), 위쪽은 +z_up (기본 15cm)으로 임시 설정
  - Y/A/X를 눌러도 끝나지 않음 (그냥 화면에 표시)

조작: 왼쪽 스틱 앞뒤(x)/좌우(y), 오른쪽 스틱 위아래 높이(z), R2 닫기 / L2 열기, SELECT(Back) 또는 Ctrl+C 종료
종료해도 팔은 마지막 자세를 유지한다 (힘이 안 빠짐).

사용:
  python teleop_test.py
  python teleop_test.py --margin 0.04      # 임시 상자를 ±4cm로
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

import lerobot_plugins  # noqa: F401  (remote_gamepad 등록)
from lerobot_plugins import RemoteGamepad

import draccus
from lerobot.model.kinematics import RobotKinematics
from lerobot.processor import TransitionKey
from lerobot.rl.gym_manipulator import (
    GymManipulatorConfig,
    make_processors,
    make_robot_env,
    reset_and_build_transition,
    step_env_and_process_transition,
)
from lerobot.teleoperators.utils import TeleopEvents
from lerobot.utils.robot_utils import precise_sleep

HERE = Path(__file__).resolve().parent


def sync_goal_to_present(port: str) -> None:
    """토크가 꺼져 있으면 Goal_Position이 0 등 엉뚱한 값으로 남아 있을 수 있다 (실제로 전부 0이었음).
    lerobot connect는 목표를 안 맞추고 토크를 켜므로, 켜는 순간 팔이 튀지 않게 목표 = 현재 위치로 먼저 써 둔다."""
    from lerobot.motors import Motor, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus

    names = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
    bus = FeetechMotorsBus(port, {n: Motor(i + 1, "sts3215", MotorNormMode.RANGE_M100_100) for i, n in enumerate(names)})
    bus.connect(handshake=False)
    try:
        present = bus.sync_read("Present_Position", normalize=False)
        bus.sync_write("Goal_Position", present, normalize=False)
        goal = bus.sync_read("Goal_Position", normalize=False)
        if any(abs(goal[n] - present[n]) > 5 for n in names):
            raise RuntimeError(f"목표 위치 맞추기 실패: present={present} goal={goal}")
    finally:
        bus.port_handler.closePort()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=HERE / "configs" / "flower_hil.json")
    parser.add_argument("--margin", type=float, default=0.06, help="임시 작업 영역: 지금 끝단 위치 ± 이 값 (m)")
    parser.add_argument("--z_up", type=float, default=0.15, help="임시 작업 영역 위쪽만 따로: 지금 높이 + 이 값 (m)")
    args = parser.parse_args()

    raw = json.loads(args.config.read_text())
    raw["env"]["robot"]["cameras"] = {}
    raw["env"]["processor"]["reset"]["fixed_reset_joint_positions"] = None
    raw["env"]["processor"]["reset"]["control_time_s"] = 1e6  # 시간 제한 없음
    ik = raw["env"]["processor"]["inverse_kinematics"]
    ik["urdf_path"] = str(HERE / ik["urdf_path"])
    measured_bounds = ik["end_effector_bounds"]
    ik["end_effector_bounds"] = {"min": [0, 0, 0], "max": [0, 0, 0]}  # 아래에서 채움
    cfg = draccus.decode(GymManipulatorConfig, raw)

    sync_goal_to_present(cfg.env.robot.port)
    env, teleop = make_robot_env(cfg.env)
    assert isinstance(teleop, RemoteGamepad)
    teleop.config.always_intervene = True

    try:
        motor_names = list(env.robot.bus.motors)
        kin = RobotKinematics(ik["urdf_path"], ik["target_frame_name"], motor_names)
        pos = env.robot.bus.sync_read("Present_Position")
        ee = kin.forward_kinematics(np.array([pos[n] for n in motor_names], dtype=float))[:3, 3]
        print(f"\n지금 끝단 위치 (m, 로봇 바닥 기준 x 앞 / y 왼쪽 / z 위): {np.round(ee, 3)}")
        if measured_bounds is not None:
            bounds = measured_bounds
            print("작업 영역: config의 측정값 사용")
        else:
            hi = ee + args.margin
            hi[2] = ee[2] + args.z_up
            bounds = {"min": (ee - args.margin).tolist(), "max": hi.tolist()}
            print(
                f"작업 영역: 임시 상자 = 지금 위치 ±{args.margin * 100:.0f}cm, 위로 +{args.z_up * 100:.0f}cm"
                " (벗어나는 방향으로는 안 감)"
            )
        print(f"  min {np.round(bounds['min'], 3)}  max {np.round(bounds['max'], 3)}")
        cfg.env.processor.inverse_kinematics.end_effector_bounds = bounds

        env_processor, action_processor = make_processors(env, teleop, cfg.env, cfg.device)
        transition = reset_and_build_transition(env, env_processor, action_processor)
        neutral = torch.tensor([0.0, 0.0, 0.0, 1.0], dtype=torch.float32)
        fps = cfg.env.fps

        print("\n조종 시작. 왼쪽 스틱 앞뒤/좌우, 오른쪽 스틱 높이, R2 닫기 / L2 열기, SELECT 또는 Ctrl+C 종료\n")
        teleop.clear_pressed()
        while True:
            t = time.perf_counter()
            if teleop.pop_pressed("back"):
                break
            transition = step_env_and_process_transition(env, transition, neutral, env_processor, action_processor)
            a = transition[TransitionKey.COMPLEMENTARY_DATA].get("teleop_action")
            info = transition[TransitionKey.INFO]
            ev = [name for k, name in ((TeleopEvents.SUCCESS, "Y"), (TeleopEvents.RERECORD_EPISODE, "X")) if info.get(k)]
            joints = env.get_raw_joint_positions()
            j = np.array([joints[f"{n}.pos"] for n in motor_names], dtype=float)
            ee = kin.forward_kinematics(j)[:3, 3]
            a_str = " ".join(f"{v:+.2f}" for v in a.tolist()) if a is not None else "-"
            print(
                f"\r{'패드OK' if teleop.is_live() else '패드없음'}  stick[{a_str}]  "
                f"EE x={ee[0]:.3f} y={ee[1]:.3f} z={ee[2]:.3f}  gripper={j[-1]:5.1f}"
                + (f"  (버튼 {' '.join(ev)})" if ev else "")
                + "   ",
                end="",
                flush=True,
            )
            if transition.get(TransitionKey.DONE) or transition.get(TransitionKey.TRUNCATED):
                # 실패(A)/다시(X)로 끝난 것 -> 그 자리에서 계속
                transition = reset_and_build_transition(env, env_processor, action_processor)
            precise_sleep(max(1 / fps - (time.perf_counter() - t), 0.0))
    except KeyboardInterrupt:
        pass
    finally:
        print("\n종료 (팔은 마지막 자세 유지)")
        teleop.disconnect()
        env.close()


if __name__ == "__main__":
    main()
