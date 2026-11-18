"""
SO-101 "손으로 가르치고 재생" 방식으로 LeRobotDataset을 녹화하는 스크립트 (VLA 학습용).

리더 암 없이 사람 손 궤적을 얻기 위한 방식:
  1) 시연: 토크를 끄고 팔을 손으로 직접 잡고 움직여서 작업을 보여준다 -> 관절 궤적만 기록
  2) 재생: 물체를 시연 전 위치로 되돌린 뒤, 로봇이 그 궤적을 그대로 재생하는 동안
     카메라 + 관절을 데이터셋에 기록한다 (그래서 영상에 사람 손이 안 찍힌다)
키보드 관절 조종보다 여러 관절이 동시에 자연스럽게 움직이는 궤적이 나온다.

lerobot-record를 안 쓰고 따로 만든 이유:
  - lerobot-record는 카메라를 lerobot 기본 OpenCVCamera로 열어서 WSL+usbipd에서
    'Bad file descriptor'로 실패함 -> usbip_camera.UsbipOpenCVCamera를 써야 함
  - 위의 시연/재생 2단계 흐름이 필요함

저장 형식은 lerobot-record와 동일한 LeRobotDataset v3라서 SmolVLA 등 lerobot 정책
학습(lerobot-train --dataset.repo_id=... --dataset.root=...)에 그대로 넣을 수 있다.
  observation.state          : 관절 6개 현재 위치 (float32[6])
  observation.images.<cam>   : 카메라 영상 (mp4로 인코딩 저장)
  action                     : 재생 시 모터에 보낸 관절 목표값 = 시연 궤적 (float32[6])
  task                       : 자연어 지시문 (--task, 에피소드마다 숫자 키로 선택)

사용 예 (보통은 record_flower_reach.sh로 실행):
  python record_dataset.py --repo-id local/flower_reach \\
      --task "Move the gripper close to the pink rose." \\
      --task "Move the gripper close to the yellow sunflower."
  ... --resume   # 이어서 녹화
  ... --robot-port /dev/ttyACM1 --camera /dev/video2   # 장치 번호가 다를 때

--task를 여러 번 주면 대기 상태에서 1, 2, ... 키로 이번 에피소드의 지시문을 고른다.
지시문으로 목표를 구분하게 하려면 장면에 꽃들을 항상 같이 두고 위치를 섞어가며 녹화할 것
(한 종류만 놓고 찍으면 모델이 지시문을 무시하고 "보이는 꽃으로 가기"만 배운다).

조작:
  [대기]      Q/A W/S E/D R/F T/G Y/H: 관절 키보드 조종 (위 줄 +, 아래 줄 -)
              O: 현재 자세를 시작 자세로 저장   Z: 시작 자세로 이동
              Space: 시작 자세로 이동 -> 3초 카운트다운 -> 토크 OFF, 시연 기록 시작
  [시연 중]   Space: 시연 끝 (토크 ON)   X: 시연 버림
  [재생 대기] 물체를 시연 전 위치로 되돌린 뒤 Space: 재생+녹화   X: 시연 버림
  [재생 중]   X: 중단 (이번 녹화 버림)
  [재생 후]   Space: 저장   R: 물체 재배치 후 다시 재생   X: 버림
  ESC: 종료 (저장 안 한 에피소드는 버림)

⚠️ 토크가 꺼지면 팔이 중력으로 떨어진다. 카운트다운 동안 반드시 팔을 손으로 받치고 있을 것.
그리퍼는 쓰지 않는 작업이라 시연 중에도 토크를 유지하고, 시연 시작 시점 값으로 고정해서 기록한다
(데이터셋 차원은 6개 그대로 -> 나중에 그리퍼 쓰는 작업과 같은 형식).

미리보기: Windows 브라우저에서 http://localhost:8080
"""
from __future__ import annotations

import argparse
import itertools
import json
import select
import sys
import termios
import time
import tty
from pathlib import Path

import cv2

from lerobot.cameras import ColorMode
from lerobot.cameras.opencv import OpenCVCameraConfig
from lerobot.datasets import LeRobotDataset, VideoEncodingManager
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
from lerobot.utils.constants import ACTION, OBS_STR
from lerobot.utils.feature_utils import build_dataset_frame, combine_feature_dicts, hw_to_dataset_features

from usbip_camera import MjpegServer, UsbipOpenCVCamera

DEFAULT_ROBOT_PORT = "/dev/ttyACM0"  # WSL에서 usbipd로 넘겨받은 포트 (--robot-port로 변경)
ROBOT_ID = "my_follower_arm"

# key -> (모터 이름, 방향). 대기 상태에서 자세 맞출 때만 사용
KEY_MAP = {
    "q": ("shoulder_pan", +1),
    "a": ("shoulder_pan", -1),
    "w": ("shoulder_lift", +1),
    "s": ("shoulder_lift", -1),
    "e": ("elbow_flex", +1),
    "d": ("elbow_flex", -1),
    "r": ("wrist_flex", +1),
    "f": ("wrist_flex", -1),
    "t": ("wrist_roll", +1),
    "g": ("wrist_roll", -1),
    "y": ("gripper", +1),
    "h": ("gripper", -1),
}
JOINT_SPEED = 45.0  # 키를 누르고 있을 때 초당 이동량 (관절: deg/s, 그리퍼: 0~100 스케일/s). --fps와 무관하게 일정
MAX_LEAD = 10.0  # 목표값이 현재 위치보다 이만큼 이상 앞서가지 않게 제한 (관절 한계에 막혔을 때 목표만 계속 쌓이는 것 방지)
ACTIVE_WINDOW_S = 0.15  # 이 시간 안에 같은 키 입력이 또 들어오면 "누르고 있는 중"으로 간주 (OS 키 자동 반복 이용)

MOVE_SPEED = 30.0  # 시작 자세 / 재생 시작점으로 이동할 때 속도 (deg/s). 가장 많이 움직이는 관절 기준
MOVE_MIN_S = 1.0  # 이동 시간 최소값
SETTLE_S = 0.5  # 도착 후 대기 (흔들림 가라앉히기)
TEACH_COUNTDOWN_S = 3  # 토크 끄기 전 카운트다운 (그동안 팔을 손으로 받칠 것)
MIN_TEACH_S = 0.5  # 이보다 짧은 시연은 실수로 보고 버림
MAX_TRAJ_SPEED = 450.0  # 시연 궤적에서 관절 속도가 이보다 빠르면(deg/s) 재생 거부. 한 프레임 허용치 = 이 값 / fps
DEFAULT_START_POSE = Path(__file__).parent / "start_pose.json"

DEFAULT_CAMERA = "/dev/video0"  # usbipd로 재연결할 때마다 번호가 바뀔 수 있음 (--camera로 변경, setup_session.sh가 알려줌)
CAMERA_NAME = "front"  # -> observation.images.front. 카메라를 추가하면 이름을 바꿔서 구분
CAM_WIDTH = 640
CAM_HEIGHT = 480
HTTP_PORT = 8080
# 카메라(usbip)가 가끔 0.5초 넘게 멈춤. 미리보기/대기/시연 중엔 오래된 프레임을 그대로 쓰고,
# 데이터로 저장되는 재생 중에만 이보다 오래 멈추면 그 에피소드를 버린다 (같은 장면이 여러 프레임 저장되는 것 방지)
REC_MAX_FRAME_AGE_MS = 1000
PREVIEW_MAX_FRAME_AGE_MS = 30_000  # 30초 넘게 멈추면 카메라가 끊긴 것 -> 에러로 종료

IDLE, TEACH, WAIT_REPLAY, REVIEW = "idle", "teach", "wait_replay", "review"
GRIPPER = "gripper"  # 시연 중에도 토크 유지, 궤적에서 값 고정 (그리퍼를 쓰지 않는 작업)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True, help="데이터셋 이름. 예: local/flower_pick")
    parser.add_argument(
        "--task",
        action="append",
        required=True,
        help="자연어 지시문 (VLA 입력). 여러 번 주면 숫자 키 1~9로 에피소드마다 선택",
    )
    parser.add_argument(
        "--flower",
        action="append",
        default=None,
        help="--task와 같은 순서의 꽃 이름 (예: rose). 주면 L 키로 꽃병 칸 배치를 고르고 에피소드마다 기록",
    )
    parser.add_argument(
        "--layout",
        default=None,
        help="시작할 때 꽃병 배치. 1번칸부터 꽃 이름을 쉼표로 (예: sunflower,rose,blue)",
    )
    parser.add_argument(
        "--layouts",
        default=None,
        help="쓸 배치 목록만 (기본: 모든 순열). 배치를 ';'로, 칸을 ','로. 예: sunflower,rose,blue;rose,blue,sunflower",
    )
    parser.add_argument(
        "--per-layout",
        type=int,
        default=30,
        help="배치 하나당 모을 에피소드 수 (꽃마다 이 값 / 꽃 수). 다 모이면 다음 배치로 바꾸라고 알려줌",
    )
    parser.add_argument(
        "--order",
        choices=["balanced", "sequential"],
        default="balanced",
        help="다음 추천 꽃 (저장·배치 변경 때 지시문이 이 꽃으로 자동 전환): balanced = 가장 적게 모인 꽃 / sequential = --task 순서대로 한 꽃을 다 채운 뒤 다음 꽃",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="저장 위치. 기본: ~/lerobot_data/<repo-id>. /mnt/c 밑은 느리므로 WSL 홈 권장",
    )
    parser.add_argument("--robot-port", default=DEFAULT_ROBOT_PORT, help="로봇 시리얼 포트 (ls /dev/ttyACM*)")
    parser.add_argument("--camera", default=DEFAULT_CAMERA, help="카메라 장치 (setup_session.sh 출력 참고)")
    parser.add_argument("--camera-source", choices=["usbip", "net"], default="usbip",
                        help="usbip = WSL에 붙인 카메라 / net = Windows camera_sender_windows.py가 보내는 사진")
    parser.add_argument("--net-camera-port", type=int, default=5558)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--episode-time-s", type=float, default=60, help="시연 최대 길이. 넘으면 자동으로 시연 종료")
    parser.add_argument("--resume", action="store_true", help="기존 데이터셋에 에피소드를 이어서 추가")
    parser.add_argument(
        "--push",
        choices=["private", "public"],
        default=None,
        help="종료할 때 Hugging Face Hub에 업로드 (repo-id가 '<HF아이디>/<이름>' 형식이어야 함, hf auth login 필요)",
    )
    parser.add_argument(
        "--start-pose",
        type=Path,
        default=DEFAULT_START_POSE,
        help="시작 자세 파일 (O 키로 저장). 작업마다 다른 시작 자세를 쓰려면 파일을 따로 지정",
    )
    return parser.parse_args()


def read_keys() -> list[str]:
    """non-blocking으로 stdin에 와 있는 입력을 전부 읽는다."""
    keys = []
    while select.select([sys.stdin], [], [], 0)[0]:
        keys.append(sys.stdin.read(1))
    return keys


def main():
    args = parse_args()
    if args.push and args.repo_id.startswith("local/"):
        raise ValueError("--push를 쓰려면 --repo-id를 '<HF아이디>/<이름>' 형식으로 (예: parkjoonsang/flower_reach)")
    root = args.root or Path.home() / "lerobot_data" / args.repo_id

    follower = SO101Follower(SO101FollowerConfig(port=args.robot_port, id=ROBOT_ID))
    if args.camera_source == "net":
        # Windows camera_sender_windows.py가 보내는 사진 (usbip로 넘기면 6~7 fps, 11-17 실측)
        from net_camera import NetCamera
        camera = NetCamera(port=args.net_camera_port, width=CAM_WIDTH, height=CAM_HEIGHT)
    else:
        camera = UsbipOpenCVCamera(
            OpenCVCameraConfig(
                index_or_path=args.camera,
                fourcc="MJPG",
                width=CAM_WIDTH,
                height=CAM_HEIGHT,
                fps=30,
                color_mode=ColorMode.RGB,
            )
        )

    features = combine_feature_dicts(
        hw_to_dataset_features(follower.action_features, ACTION, use_video=True),
        hw_to_dataset_features(
            {**follower.observation_features, CAMERA_NAME: (CAM_HEIGHT, CAM_WIDTH, 3)}, OBS_STR, use_video=True
        ),
    )

    if args.resume:
        dataset = LeRobotDataset.resume(args.repo_id, root=root, image_writer_threads=4)
        if dataset.fps != args.fps:
            raise ValueError(f"기존 데이터셋 fps={dataset.fps}와 --fps={args.fps}가 다릅니다.")
    else:
        if root.exists():
            raise FileExistsError(f"{root} 가 이미 있습니다. 이어서 녹화하려면 --resume 을 붙이세요.")
        dataset = LeRobotDataset.create(
            args.repo_id,
            args.fps,
            features=features,
            root=root,
            robot_type=follower.name,
            use_videos=True,
            image_writer_threads=4,
        )

    mjpeg = MjpegServer(port=HTTP_PORT, fps=args.fps)
    camera.connect()
    follower.connect()

    motors = list(follower.bus.motors)
    dt = 1.0 / args.fps
    step = JOINT_SPEED / args.fps

    def read_pose() -> dict[str, float]:
        o = follower.get_observation()
        return {m: float(o[f"{m}.pos"]) for m in motors}

    target = read_pose()

    start_pose: dict[str, float] | None = None
    if args.start_pose.exists():
        start_pose = json.loads(args.start_pose.read_text())
        if set(start_pose) != set(motors):
            raise ValueError(f"{args.start_pose}의 모터 목록 {sorted(start_pose)}가 로봇 {sorted(motors)}와 다릅니다.")

    print(f"데이터셋: {root}  (기존 에피소드 {dataset.num_episodes}개)")
    if len(args.task) > 9:
        raise ValueError("--task는 최대 9개까지 (숫자 키 1~9)")
    task_idx = 0
    for i, t in enumerate(args.task):
        print(f"task {i + 1}: {t}")
    if len(args.task) > 1:
        print("   대기 상태에서 숫자 키로 이번 에피소드 지시문 선택 (현재: 1)")

    # ----- 꽃병 칸 배치 기록 (핸드오프 분석에서 꽃 위치 p_f를 칸 번호로 알기 위해) -----
    flowers = args.flower or []
    if flowers and len(flowers) != len(args.task):
        raise ValueError(f"--flower {len(flowers)}개와 --task {len(args.task)}개 수가 다릅니다 (같은 순서로 하나씩 주세요)")
    layouts = list(itertools.permutations(range(len(flowers)))) if flowers else []  # layouts[j][칸] = 꽃 번호
    if flowers and args.layouts:
        chosen = []
        for spec in args.layouts.split(";"):
            names = [n.strip() for n in spec.split(",")]
            if sorted(names) != sorted(flowers):
                raise ValueError(f"--layouts 의 {names} 은 꽃 {flowers} 를 한 번씩 써야 합니다")
            chosen.append(tuple(flowers.index(n) for n in names))
        layouts = chosen
    layout_idx = 0
    if flowers and args.layout:
        names = [n.strip() for n in args.layout.split(",")]
        if sorted(names) != sorted(flowers):
            raise ValueError(f"--layout {names} 은 꽃 {flowers} 를 한 번씩 써야 합니다")
        layout_idx = layouts.index(tuple(flowers.index(n) for n in names))
    log_path = root.parent / f"{root.name}_collection_log.jsonl"
    counts: dict[tuple[int, int], int] = {}  # (배치 번호, 지시문 번호) -> 에피소드 수
    if flowers and log_path.exists():
        for line in log_path.read_text().splitlines():
            rec = json.loads(line)
            if rec["episode_index"] < dataset.num_episodes:
                lay = tuple(flowers.index(rec["layout"][str(s + 1)]) for s in range(len(flowers)))
                if lay not in layouts:
                    continue   # --layouts 로 뺀 배치의 기록
                k = (layouts.index(lay), rec["task_index"])
                counts[k] = counts.get(k, 0) + 1
    per_flower = max(1, args.per_layout // max(1, len(flowers)))

    def layout_text(j: int) -> str:
        return "  ".join(f"{s + 1}번칸={flowers[f]}" for s, f in enumerate(layouts[j]))

    def suggest() -> int | None:
        """지금 배치에서 가장 적게 모인 꽃을 추천(번호 반환). 배치가 다 차면 아직 덜 찬 배치로 바꾸라고 알림."""
        here = [counts.get((layout_idx, t), 0) for t in range(len(flowers))]
        print("   지금 배치 진행: " + "  ".join(f"{flowers[t]} {n}/{per_flower}" for t, n in enumerate(here)))
        if min(here) < per_flower:
            if args.order == "sequential":
                t = next(i for i, n in enumerate(here) if n < per_flower)
            else:
                t = here.index(min(here))
            print(f"   다음 추천: {t + 1}번 지시문 ({flowers[t]}, {layouts[layout_idx].index(t) + 1}번 칸)")
            return t
        todo = [j for j in range(len(layouts))
                if min(counts.get((j, t), 0) for t in range(len(flowers))) < per_flower]
        if todo:
            print(f"   ✅ 이 배치 완료! 꽃을 바꿔 꽂고 L로 배치 {todo[0] + 1} ({layout_text(todo[0])}) 로 맞추세요")
        else:
            print(f"   ✅ 모든 배치 {len(layouts)}개 완료 (총 {sum(counts.values())}개)")
        return None

    if flowers and not args.layout:
        # 다시 켤 때 배치 1로 돌아가면 다 찬 배치로 찍힘 (11-16 ep109 사고) → 아직 덜 찬 첫 배치로 시작
        todo = [j for j in range(len(layouts))
                if min(counts.get((j, t), 0) for t in range(len(flowers))) < per_flower]
        if todo:
            layout_idx = todo[0]
    if flowers:
        print(f"꽃 배치 기록: {log_path}")
        print(f"   L: 배치 바꾸기 ({len(layouts)}가지). 현재 배치 {layout_idx + 1}: {layout_text(layout_idx)}")
        print(f"   ⚠️ 실제 꽃병이 이 배치인지 확인하세요 (다르면 L)")
        t = suggest()
        if t is not None:
            task_idx = t  # 다시 켤 때 1번(rose)으로 돌아가서 엉뚱한 지시문으로 찍히는 것 방지
    print(f"\n>>> 현재 지시문 {task_idx + 1}: {args.task[task_idx]}  (바꾸려면 숫자 키) <<<\n")
    print(f"미리보기: Windows 브라우저에서 http://localhost:{HTTP_PORT}")
    if start_pose is None:
        print(f"시작 자세: 없음 -> 원하는 자세로 맞춘 뒤 O를 눌러 저장하세요 ({args.start_pose})")
    else:
        print(f"시작 자세: {args.start_pose}  " + ", ".join(f"{m}={v:.1f}" for m, v in start_pose.items()))
    print("[대기] 관절 키보드 조종   O 시작자세 저장   Z 시작자세로 이동   Space 시연 시작   ESC 종료"
          + ("   L 꽃 배치 바꾸기" if flowers else "") + "\n")

    def show_preview(img, label: str | None = None) -> None:
        preview = img.copy()
        if label:
            cv2.circle(preview, (20, 20), 8, (255, 0, 0), -1)
            cv2.putText(preview, label, (35, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        mjpeg.update(preview)

    def move_to(pose: dict[str, float], label: str) -> None:
        """현재 위치에서 pose까지 부드럽게 보간 이동 (블로킹). 이동 중 키 입력은 버린다."""
        begin = read_pose()
        dist = max(abs(pose[m] - begin[m]) for m in motors)
        n_steps = max(1, int(max(MOVE_MIN_S, dist / MOVE_SPEED) * args.fps))
        n_settle = int(SETTLE_S * args.fps)

        for i in range(1, n_steps + n_settle + 1):
            t0 = time.perf_counter()
            a = min(1.0, i / n_steps)
            a = a * a * (3 - 2 * a)  # smoothstep: 출발/도착을 부드럽게
            follower.send_action({f"{m}.pos": begin[m] + a * (pose[m] - begin[m]) for m in motors})
            show_preview(camera.read_latest(max_age_ms=PREVIEW_MAX_FRAME_AGE_MS), label)
            time.sleep(max(0.0, dt - (time.perf_counter() - t0)))

        target.update(pose)
        read_keys()
        last_seen.clear()

    def hold_here_and_enable_torque() -> None:
        """토크를 켜기 전에 목표 위치를 현재 위치로 써둬야 켜는 순간 예전 목표로 튀지 않는다."""
        pose = read_pose()
        follower.send_action({f"{m}.pos": v for m, v in pose.items()})
        follower.bus.enable_torque()
        target.update(pose)
        last_seen.clear()

    def replay(traj: list[dict[str, float]]) -> bool:
        """시연 궤적을 재생하면서 데이터셋 버퍼에 기록. X/ESC로 중단하면 False."""
        # 안전장치: 궤적에 한 프레임 사이 큰 점프가 있으면 재생하지 않는다 (모터가 급격히 튐)
        for i in range(1, len(traj)):
            jump = max(abs(traj[i][m] - traj[i - 1][m]) for m in motors)
            if jump > MAX_TRAJ_SPEED / args.fps:
                print(f"\n⚠️ 시연 궤적 {i}번째 프레임에서 {jump:.1f}도 점프 -> 재생 안 함. X로 버리고 다시 시연하세요.")
                return False
        move_to(traj[0], "MOVING TO REPLAY START")
        corrupt0, good0 = camera.corrupt_frames, camera.good_frames
        cam_frames, last_ts, overruns = 0, None, 0
        t_start = time.perf_counter()

        for i, pose in enumerate(traj):
            t0 = time.perf_counter()
            if any(ch == "\x1b" or ch.lower() == "x" for ch in read_keys()):
                dataset.clear_episode_buffer()
                hold_here_and_enable_torque()
                print("\n[재생 중단] 이번 녹화 버림")
                return False

            obs = follower.get_observation()
            try:
                img = camera.read_latest(max_age_ms=REC_MAX_FRAME_AGE_MS)
            except TimeoutError:
                dataset.clear_episode_buffer()
                hold_here_and_enable_torque()
                print(f"\n⚠️ 카메라가 {REC_MAX_FRAME_AGE_MS}ms 넘게 멈춰서 이번 녹화를 버림 (USB 끊김 의심). "
                      "물체를 되돌리고 Space로 다시 재생")
                return False
            with camera.frame_lock:
                ts = camera.latest_timestamp
            if ts != last_ts:
                cam_frames, last_ts = cam_frames + 1, ts

            sent = follower.send_action({f"{m}.pos": v for m, v in pose.items()})
            dataset.add_frame(
                {
                    **build_dataset_frame(dataset.features, {**obs, CAMERA_NAME: img}, prefix=OBS_STR),
                    **build_dataset_frame(dataset.features, sent, prefix=ACTION),
                    "task": args.task[task_idx],
                }
            )
            show_preview(img, f"REC ep{dataset.num_episodes} {i + 1}/{len(traj)}")

            elapsed = time.perf_counter() - t0
            if elapsed > dt:
                overruns += 1
            time.sleep(max(0.0, dt - elapsed))

        target.update(traj[-1])
        duration = time.perf_counter() - t_start
        cam_fps = cam_frames / duration if duration > 0 else 0
        corrupt = camera.corrupt_frames - corrupt0
        good = camera.good_frames - good0
        print(f"\n[재생 완료] {len(traj)} frames, {duration:.1f}s")
        print(f"   카메라 실제 {cam_fps:.1f} fps / 루프 지연 {overruns}회 (데이터셋 {args.fps} fps)")
        if corrupt:
            print(f"   손상 프레임 {corrupt}개 버림 ({corrupt / max(1, corrupt + good):.0%}) - 저장 영상에는 안 들어감")
        if cam_fps < args.fps * 0.8:
            print("   ⚠️ 카메라가 데이터셋 fps보다 느려서 같은 프레임이 반복 저장되고 있음. --fps를 낮추는 것 고려")
        return True

    last_seen: dict[str, float] = {}
    state = IDLE
    traj: list[dict[str, float]] = []
    teach_start = 0.0
    gripper_fixed = target[GRIPPER]
    saved_per_task = [0] * len(args.task)

    fd = sys.stdin.fileno()
    old_term_settings = termios.tcgetattr(fd)

    try:
        with VideoEncodingManager(dataset):
            tty.setcbreak(fd)
            running = True
            while running:
                loop_start = time.perf_counter()
                obs = follower.get_observation()
                frame_img = camera.read_latest(max_age_ms=PREVIEW_MAX_FRAME_AGE_MS)

                # ----- 키 입력 (상태별) -----
                # 이동/카운트다운/재생처럼 시간이 걸리는 동작을 하면 위에서 읽은 obs가 옛날 값이 된다.
                # 그 obs로 시연 첫 프레임을 기록했다가 궤적 첫 점이 "이전 에피소드 끝 위치"가 되는 버그가
                # 있었으므로(재생 시 1프레임 만에 수십 도 점프), 그런 동작 뒤에는 이번 반복을 버리고 새로 읽는다.
                stale = False
                for ch in read_keys():
                    key = ch.lower()
                    if ch == "\x1b":  # ESC
                        running = False
                        break
                    if stale:
                        continue  # 블로킹 동작 이후 같은 배치의 키는 무시

                    if state == IDLE:
                        if ch.isdigit() and 1 <= int(ch) <= len(args.task):
                            task_idx = int(ch) - 1
                            print(f"[지시문 {ch}] {args.task[task_idx]}")
                        elif key == "l" and flowers:
                            layout_idx = (layout_idx + 1) % len(layouts)
                            print(f"[배치 {layout_idx + 1}] {layout_text(layout_idx)}")
                            t = suggest()
                            if t is not None and t != task_idx:  # sequential·balanced 모두 추천 꽃으로 자동 전환 (숫자 키로 바꿀 수 있음)
                                task_idx = t   # 배치 바꾸면 그 배치의 첫 꽃(rose)부터 (11-16: 이전 배치 sunflower로 찍힌 사고)
                                print(f"\n>>> {flowers[t]} 차례: 지시문 {t + 1}로 자동 변경 — {args.task[t]} <<<\n")
                        elif key == "o":
                            start_pose = {m: round(float(obs[f"{m}.pos"]), 2) for m in motors}
                            args.start_pose.write_text(json.dumps(start_pose, indent=2))
                            print("[시작 자세 저장] " + ", ".join(f"{m}={v:.1f}" for m, v in start_pose.items()))
                        elif key == "z":
                            if start_pose is None:
                                print("[시작 자세가 없음 -> O로 먼저 저장]")
                            else:
                                move_to(start_pose, "MOVING TO START")
                                stale = True
                        elif ch == " ":
                            if start_pose is not None:
                                move_to(start_pose, "MOVING TO START")
                            else:
                                print("⚠️ 시작 자세가 없어서 현재 자세에서 시작 (O로 저장하면 고정됨)")
                            print(f"[시연 준비] 팔을 손으로 받치세요. {TEACH_COUNTDOWN_S}초 뒤 토크가 꺼집니다.")
                            for sec in range(TEACH_COUNTDOWN_S, 0, -1):
                                print(f"   {sec}...")
                                t_end = time.perf_counter() + 1.0
                                while time.perf_counter() < t_end:
                                    show_preview(camera.read_latest(max_age_ms=PREVIEW_MAX_FRAME_AGE_MS), f"HOLD THE ARM {sec}")
                                    time.sleep(dt)
                            # 그리퍼는 토크 유지 + 값 고정 (작업이 꽃 근처로 이동뿐이라 그리퍼 안 씀)
                            gripper_fixed = target[GRIPPER]
                            follower.bus.disable_torque([m for m in motors if m != GRIPPER])
                            read_keys()
                            traj, teach_start, state = [], time.perf_counter(), TEACH
                            stale = True
                            print(f"[시연 중] '{args.task[task_idx]}'  Space 끝   X 버림")
                        else:
                            last_seen[key] = loop_start

                    elif state == TEACH:
                        if ch == " " or key == "x":
                            hold_here_and_enable_torque()
                            stale = True
                            if key == "x":
                                print("[시연 버림]")
                                state = IDLE
                            elif len(traj) < MIN_TEACH_S * args.fps:
                                print(f"[시연이 너무 짧음 ({len(traj)} frames) -> 버림]")
                                state = IDLE
                            else:
                                print(f"[시연 완료] {len(traj)} frames, {len(traj) / args.fps:.1f}s")
                                print("   물체를 시연 전 위치로 되돌린 뒤 Space: 재생+녹화   X: 버림")
                                state = WAIT_REPLAY

                    elif state == WAIT_REPLAY:
                        if ch == " ":
                            state = REVIEW if replay(traj) else WAIT_REPLAY
                            stale = True
                            if state == REVIEW:
                                print("   Space: 저장   R: 물체 재배치 후 다시 재생   X: 버림")
                            else:
                                print("   물체를 시연 전 위치로 되돌린 뒤 Space: 다시 재생   X: 버림")
                        elif key == "x":
                            print("[시연 버림]")
                            state = IDLE

                    elif state == REVIEW:
                        if ch == " ":
                            print("[저장 중...]", end="", flush=True)
                            dataset.save_episode()
                            stale = True
                            try:   # 배터리 전압 (모터 공급 전압, 0.1 V 단위). 6.6 V 미만이면 추종이 나빠지고 과부하
                                volts = follower.bus.sync_read("Present_Voltage", normalize=False)
                                vmin = min(volts.values()) / 10
                                print(f" [배터리 {vmin:.1f} V{' ⚠️ 6.6 V 미만: 충전/교체' if vmin < 6.6 else ''}]", end="")
                            except Exception as ex:
                                print(f" [전압 읽기 실패: {ex}]", end="")
                            saved_per_task[task_idx] += 1
                            print(f" -> 에피소드 {dataset.num_episodes - 1} 저장 완료 (총 {dataset.num_episodes}개)")
                            if flowers:
                                lay = layouts[layout_idx]
                                target_slot = lay.index(task_idx)
                                rec = {
                                    "episode_index": dataset.num_episodes - 1,
                                    "task_index": task_idx,
                                    "task": args.task[task_idx],
                                    "layout": {str(s + 1): flowers[f] for s, f in enumerate(lay)},
                                    "target_slot": target_slot + 1,
                                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                                }
                                with log_path.open("a") as f_log:
                                    f_log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                                k = (layout_idx, task_idx)
                                counts[k] = counts.get(k, 0) + 1
                                print(f"   기록: 목표 {flowers[task_idx]} = {target_slot + 1}번 칸 ({layout_text(layout_idx)})")
                                t = suggest()
                                if t is not None and t != task_idx:  # sequential·balanced 모두 추천 꽃으로 자동 전환 (숫자 키로 바꿀 수 있음)
                                    task_idx = t   # 한 꽃이 다 차면 다음 꽃 지시문으로 자동 전환 (지시문 잘못 찍히는 사고 방지)
                                    print(f"\n>>> {flowers[t]} 차례: 지시문 {t + 1}로 자동 변경 — {args.task[t]} <<<\n")
                            if len(args.task) > 1:
                                print(
                                    "   이번 세션: "
                                    + "  ".join(f"{i + 1}번 {n}개" for i, n in enumerate(saved_per_task))
                                )
                            state = IDLE
                        elif key == "r":
                            dataset.clear_episode_buffer()
                            print("[다시 재생] 물체를 시연 전 위치로 되돌린 뒤 Space")
                            state = WAIT_REPLAY
                        elif key == "x":
                            dataset.clear_episode_buffer()
                            print("[에피소드 버림]")
                            state = IDLE
                if not running:
                    break
                if stale:
                    continue

                # ----- 상태별 동작 -----
                if state == IDLE:
                    for key, (motor, direction) in KEY_MAP.items():
                        t = last_seen.get(key)
                        if t is None or loop_start - t >= ACTIVE_WINDOW_S:
                            continue
                        present = obs[f"{motor}.pos"]
                        new = target[motor] + direction * step
                        target[motor] = min(max(new, present - MAX_LEAD), present + MAX_LEAD)
                    target["gripper"] = min(max(target["gripper"], 0.0), 100.0)
                    follower.send_action({f"{m}.pos": v for m, v in target.items()})
                    label = f"TASK {task_idx + 1}" if len(args.task) > 1 else None
                    if flowers:
                        label = f"TASK {task_idx + 1} {flowers[task_idx]} | L{layout_idx + 1}: " + " ".join(
                            flowers[f][:4] for f in layouts[layout_idx])
                    show_preview(frame_img, label)

                elif state == TEACH:
                    traj.append({m: float(obs[f"{m}.pos"]) for m in motors} | {GRIPPER: gripper_fixed})
                    show_preview(frame_img, f"TEACH {len(traj) / args.fps:.1f}s")
                    if time.perf_counter() - teach_start >= args.episode_time_s:
                        hold_here_and_enable_torque()
                        print(f"[최대 길이 {args.episode_time_s}s 도달 -> 시연 완료] {len(traj)} frames")
                        print("   물체를 시연 전 위치로 되돌린 뒤 Space: 재생+녹화   X: 버림")
                        state = WAIT_REPLAY

                else:  # WAIT_REPLAY / REVIEW: 토크 ON 상태로 현재 목표 유지
                    show_preview(frame_img, "RESET OBJECTS" if state == WAIT_REPLAY else "SAVE? Space/R/X")

                time.sleep(max(0.0, dt - (time.perf_counter() - loop_start)))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_term_settings)
        if state == TEACH:
            try:
                hold_here_and_enable_torque()
            except Exception:
                pass
        dataset.finalize()
        follower.disconnect()
        camera.disconnect()
        print(f"\n종료. 데이터셋: {root} (에피소드 {dataset.num_episodes}개)")

    if args.push and dataset.num_episodes > 0:
        print(f"[Hub 업로드 중...] {args.repo_id} ({args.push})")
        dataset.push_to_hub(private=args.push == "private")
        print(f"업로드 완료: https://huggingface.co/datasets/{args.repo_id}")


if __name__ == "__main__":
    main()
