"""
HIL-SERL용 시연 데이터를 게임패드로 녹화한다.

lerobot 공식 녹화(python -m lerobot.rl.gym_manipulator, mode=record)와 같은 부품을 쓴다:
  make_robot_env / make_processors / step_env_and_process_transition
-> 관측 처리, EE(끝단) 이동 액션, IK, 작업 영역 제한이 나중에 HIL-SERL actor가 쓰는 것과 똑같다.
그래서 이 데이터는 learner의 오프라인(시연) 버퍼에 그대로 넣을 수 있다.

공식 녹화 루프 대신 직접 짠 이유:
  - 이어서 녹화(--resume=true)가 안 됨 (공식은 매번 새로 만들고 폴더가 있으면 에러)
  - Ctrl+C로 끄면 dataset.finalize()가 안 불려서 데이터셋이 깨질 수 있음
  - 에피소드 사이가 "5초 고정 대기"라 물체 정리 시간이 모자람 -> Start 버튼을 누를 때까지 기다림
  - WSL에서는 cv2 창이 안 뜸 -> 브라우저 미리보기에 상태 표시
  - 시연 녹화는 사람이 계속 조종하므로 RB(개입)를 누르고 있을 필요 없게 함

기록되는 것 (공식과 같음):
  observation.state           관절 6개 각도
  observation.images.front    카메라 영상 (전체 해상도. 자르기/축소는 나중에 crop 단계에서)
  action                      [dx, dy, dz, gripper]  dx~dz: -1~1 스틱 값, gripper: 0닫기/1유지/2열기
  next.reward                 성공(Y)을 누른 프레임만 1, 나머지 0
  next.done                   에피소드 마지막 프레임 True
  complementary_info.discrete_penalty  그리퍼 페널티 (gripper_penalty=0이면 항상 0)

게임패드:
  [대기]  Start: 에피소드 시작        Back: 종료
  [녹화]  왼쪽 스틱: 앞뒤(x)/좌우(y)   오른쪽 스틱 위아래: 높이(z)
          RT: 그리퍼 닫기   LT: 그리퍼 열기
          Y: 성공 -> 저장   A: 실패 -> 저장   X: 다시 찍기(버림)   Back: 버리고 종료
  시간 제한(control_time_s)을 넘기면 실패로 저장.

사용:
  python record_demos.py                                   # configs/flower_hil.json, 새 데이터셋
  python record_demos.py --resume=true                     # 이어서
  python record_demos.py --config_path=configs/다른.json --dataset.num_episodes_to_record=30
"""
# from __future__ import annotations 금지: lerobot parser.wrap이 main(cfg: DemoRecordConfig)의 타입을 실제 클래스로 읽어야 함
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

import lerobot_plugins  # noqa: F401  (usbip_camera / remote_gamepad 등록)
from lerobot_plugins import GREEN, RED, WHITE, YELLOW, RemoteGamepad, set_status

from lerobot.configs import parser
from lerobot.datasets import LeRobotDataset
from lerobot.processor import TransitionKey
from lerobot.rl.gym_manipulator import (
    GymManipulatorConfig,
    make_processors,
    make_robot_env,
    reset_and_build_transition,
    step_env_and_process_transition,
)
from lerobot.teleoperators.utils import TeleopEvents
from lerobot.utils.constants import ACTION, DONE, OBS_STATE, REWARD
from lerobot.utils.robot_utils import precise_sleep

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "configs" / "flower_hil.json"
MOVE_SPEED = 30.0  # 시작 자세로 돌아갈 때 속도 (deg/s, 가장 많이 움직이는 관절 기준)


@dataclass
class DemoRecordConfig(GymManipulatorConfig):
    resume: bool = False  # 기존 데이터셋에 이어서 녹화


def move_smooth(robot, target: list[float], fps: int = 30) -> None:
    """현재 자세에서 target(관절 각도, 모터 순서)까지 속도 제한해서 이동. 공식 reset은 거리와 상관없이 0.75초라 빠를 수 있음."""
    names = list(robot.bus.motors)
    current = robot.bus.sync_read("Present_Position")
    begin = np.array([current[n] for n in names], dtype=float)
    goal = np.array(target, dtype=float)
    n_steps = max(1, int(max(1.0, np.abs(goal - begin).max() / MOVE_SPEED) * fps))
    for i in range(1, n_steps + 1):
        a = i / n_steps
        a = a * a * (3 - 2 * a)  # smoothstep
        robot.bus.sync_write("Goal_Position", dict(zip(names, begin + a * (goal - begin), strict=True)))
        precise_sleep(1 / fps)


def build_features(transition, teleop: RemoteGamepad, use_gripper: bool) -> dict:
    """gym_manipulator.control_loop과 같은 방식으로 데이터셋 형식을 만든다."""
    features = {
        ACTION: teleop.action_features,
        REWARD: {"dtype": "float32", "shape": (1,), "names": None},
        DONE: {"dtype": "bool", "shape": (1,), "names": None},
    }
    if use_gripper:
        features["complementary_info.discrete_penalty"] = {
            "dtype": "float32",
            "shape": (1,),
            "names": ["discrete_penalty"],
        }
    for key, value in transition[TransitionKey.OBSERVATION].items():
        if key == OBS_STATE:
            features[key] = {"dtype": "float32", "shape": value.squeeze(0).shape, "names": None}
        if "image" in key:
            features[key] = {
                "dtype": "video",
                "shape": value.squeeze(0).shape,
                "names": ["channels", "height", "width"],
            }
    return features


def resolve_paths(cfg: DemoRecordConfig) -> None:
    ik = cfg.env.processor.inverse_kinematics
    if ik is not None and ik.urdf_path and not Path(ik.urdf_path).is_absolute():
        ik.urdf_path = str(HERE / ik.urdf_path)
    if cfg.dataset.root is None:
        cfg.dataset.root = str(Path.home() / "lerobot_data" / cfg.dataset.repo_id)


@parser.wrap()
def main(cfg: DemoRecordConfig) -> None:
    resolve_paths(cfg)
    reset_cfg = cfg.env.processor.reset
    if reset_cfg is None or reset_cfg.fixed_reset_joint_positions is None:
        raise ValueError("config의 env.processor.reset.fixed_reset_joint_positions가 비어 있음 -> measure_workspace.py 먼저")
    if cfg.env.processor.inverse_kinematics.end_effector_bounds is None:
        raise ValueError("config의 end_effector_bounds가 비어 있음 -> measure_workspace.py 먼저")
    reset_pose = list(reset_cfg.fixed_reset_joint_positions)
    use_gripper = cfg.env.processor.gripper.use_gripper if cfg.env.processor.gripper is not None else True
    fps = cfg.env.fps
    root = Path(cfg.dataset.root)

    if not cfg.resume and root.exists():
        raise FileExistsError(f"{root} 가 이미 있습니다. 이어서 녹화하려면 --resume=true")

    set_status("CONNECTING...", YELLOW)
    env, teleop = make_robot_env(cfg.env)
    if not isinstance(teleop, RemoteGamepad):
        raise TypeError('이 스크립트는 env.teleop.type = "remote_gamepad" 전용')
    teleop.config.always_intervene = True  # 시연은 사람이 계속 조종
    env.reset_time_s = 0.0  # 공식 env의 고정 대기 끄기 (Start 버튼으로 대신)
    env_processor, action_processor = make_processors(env, teleop, cfg.env, cfg.device)

    dataset = None
    saved = {"success": 0, "failure": 0}
    try:
        print("\n시작 자세로 이동합니다.")
        move_smooth(env.robot, reset_pose)
        transition = reset_and_build_transition(env, env_processor, action_processor)

        if cfg.resume:
            dataset = LeRobotDataset.resume(cfg.dataset.repo_id, root=root, image_writer_threads=4)
            if dataset.fps != fps:
                raise ValueError(f"기존 데이터셋 fps={dataset.fps}와 config fps={fps}가 다릅니다.")
        else:
            dataset = LeRobotDataset.create(
                cfg.dataset.repo_id,
                fps,
                root=root,
                robot_type=env.robot.name,
                use_videos=True,
                image_writer_threads=4,
                features=build_features(transition, teleop, use_gripper),
            )
        start_count = dataset.num_episodes
        target = start_count + cfg.dataset.num_episodes_to_record
        print(f"데이터셋: {root} (기존 {start_count}개, 이번 목표 {cfg.dataset.num_episodes_to_record}개)")
        print(f"task: {cfg.dataset.task}")
        print("미리보기: Windows 브라우저에서 http://localhost:8080\n")

        quit_requested = False
        while dataset.num_episodes < target and not quit_requested:
            # ---------- 대기: 물체 정리 후 Start ----------
            ep = dataset.num_episodes
            set_status(f"READY ep{ep}  Start=go  Back=quit", WHITE)
            print(f"[대기] 물체를 놓고 Start (에피소드 {ep}, 이번 세션 성공 {saved['success']} / 실패 {saved['failure']})")
            teleop.clear_pressed()
            while True:
                if teleop.pop_pressed("back"):
                    quit_requested = True
                    break
                if teleop.pop_pressed("start"):
                    break
                if not teleop.is_live():
                    set_status("GAMEPAD DISCONNECTED", RED)
                else:
                    set_status(f"READY ep{ep}  Start=go  Back=quit", WHITE)
                time.sleep(0.05)
            if quit_requested:
                break

            # ---------- 녹화 ----------
            transition = reset_and_build_transition(env, env_processor, action_processor)
            teleop.clear_pressed()
            print(f"[녹화] ep{ep}  Y 성공 / A 실패 / X 다시 / Back 버리고 종료")
            neutral = [0.0, 0.0, 0.0] + ([1.0] if use_gripper else [])
            neutral_action = torch.tensor(neutral, dtype=torch.float32)
            t0 = time.perf_counter()
            while True:
                step_start = time.perf_counter()
                if teleop.pop_pressed("back"):
                    dataset.clear_episode_buffer()
                    quit_requested = True
                    print("[종료] 녹화 중인 에피소드 버림")
                    break

                observation = {
                    k: v.squeeze(0).cpu()
                    for k, v in transition[TransitionKey.OBSERVATION].items()
                    if isinstance(v, torch.Tensor)
                }
                transition = step_env_and_process_transition(
                    env=env,
                    transition=transition,
                    action=neutral_action,
                    env_processor=env_processor,
                    action_processor=action_processor,
                )
                terminated = bool(transition.get(TransitionKey.DONE, False))
                truncated = bool(transition.get(TransitionKey.TRUNCATED, False))
                reward = float(transition[TransitionKey.REWARD])

                action_to_record = transition[TransitionKey.COMPLEMENTARY_DATA].get(
                    "teleop_action", transition[TransitionKey.ACTION]
                )
                frame = {
                    **observation,
                    ACTION: action_to_record.cpu(),
                    REWARD: np.array([reward], dtype=np.float32),
                    DONE: np.array([terminated or truncated], dtype=bool),
                    "task": cfg.dataset.task,
                }
                if use_gripper:
                    penalty = transition[TransitionKey.COMPLEMENTARY_DATA].get("discrete_penalty", 0.0)
                    frame["complementary_info.discrete_penalty"] = np.array([penalty], dtype=np.float32)
                dataset.add_frame(frame)

                elapsed = time.perf_counter() - t0
                if teleop.is_live():
                    set_status(f"REC ep{ep}  {elapsed:4.1f}/{reset_cfg.control_time_s:.0f}s  Y=ok A=fail X=redo", RED)
                else:
                    set_status("GAMEPAD DISCONNECTED - robot stopped", RED)

                if terminated or truncated:
                    info = transition[TransitionKey.INFO]
                    if info.get(TeleopEvents.RERECORD_EPISODE, False):
                        dataset.clear_episode_buffer()
                        print("   [다시 찍기] 버림")
                    else:
                        result = "success" if reward > 0 else "failure"
                        why = "성공(Y)" if reward > 0 else ("시간 초과" if truncated and not terminated else "실패(A)")
                        set_status(f"SAVING ep{ep}...", YELLOW)
                        dataset.save_episode()
                        saved[result] += 1
                        print(f"   [저장] ep{ep} {why}, {elapsed:.1f}s  (총 {dataset.num_episodes}개)")
                    break

                precise_sleep(max(1 / fps - (time.perf_counter() - step_start), 0.0))

            # ---------- 시작 자세로 복귀 ----------
            set_status("RETURNING TO START", YELLOW)
            move_smooth(env.robot, reset_pose)

    except KeyboardInterrupt:
        print("\n[Ctrl+C] 녹화 중이던 에피소드는 버림")
        if dataset is not None:
            dataset.clear_episode_buffer()
    finally:
        set_status("STOPPED", WHITE)
        if dataset is not None:
            dataset.finalize()
        teleop.disconnect()
        env.close()  # config에서 disable_torque_on_disconnect=false라 팔은 마지막 자세를 유지함
        if dataset is not None:
            print(
                f"\n종료. {root}  총 {dataset.num_episodes}개 "
                f"(이번 세션 성공 {saved['success']} / 실패 {saved['failure']})"
            )

    if dataset is not None and cfg.dataset.push_to_hub and dataset.num_episodes > 0:
        print(f"[Hub 업로드 중...] {cfg.dataset.repo_id}")
        dataset.push_to_hub()
        print(f"업로드 완료: https://huggingface.co/datasets/{cfg.dataset.repo_id}")


if __name__ == "__main__":
    if not any(a.startswith("--config_path") for a in sys.argv[1:]):
        sys.argv.append(f"--config_path={DEFAULT_CONFIG}")
    main()
