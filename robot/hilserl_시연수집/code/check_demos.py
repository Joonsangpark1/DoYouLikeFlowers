"""
record_demos.py로 녹화한 HIL-SERL 시연 데이터 점검.

에피소드별로 출력:
  - 길이, 결과(성공=마지막 프레임 reward 1 / 실패)
  - 스틱을 놓고 가만히 있던 프레임 비율 (높으면 "가만히 있기"를 배움)
  - 그리퍼 명령 횟수 (닫기/열기)
  - done/reward가 형식에 맞는지 (done은 마지막 프레임만, reward는 성공 에피소드 마지막 프레임만 1)

사용:
  python check_demos.py                                    # configs/flower_hil.json의 데이터셋
  python check_demos.py --repo-id parkjoonsang/flower_hil_demo
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from lerobot.datasets import LeRobotDataset

HERE = Path(__file__).resolve().parent
IDLE_WARN = 0.4  # 가만히 있는 프레임이 이 비율보다 많으면 경고


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=HERE / "configs" / "flower_hil.json")
    parser.add_argument("--repo-id", default=None, help="기본: config의 dataset.repo_id")
    parser.add_argument("--root", type=Path, default=None, help="기본: ~/lerobot_data/<repo-id>")
    args = parser.parse_args()

    repo_id = args.repo_id or json.loads(args.config.read_text())["dataset"]["repo_id"]
    root = args.root or Path.home() / "lerobot_data" / repo_id
    ds = LeRobotDataset(repo_id, root=root)
    cols = ["action", "next.reward", "next.done", "episode_index"]
    data = ds.hf_dataset.select_columns(cols).with_format("numpy")
    action = np.stack(data["action"])
    reward = np.asarray(data["next.reward"]).reshape(-1)
    done = np.asarray(data["next.done"]).reshape(-1)
    ep_idx = np.asarray(data["episode_index"])
    has_gripper = action.shape[1] == 4

    print(f"{repo_id}: 에피소드 {ds.num_episodes}개, {len(action)} frames, {ds.fps} fps")
    print(f"영상 키: {ds.meta.camera_keys}  상태 크기: {ds.features['observation.state']['shape']}\n")
    print(f"{'ep':>4} {'길이':>7} {'결과':>6} {'정지비율':>8} {'닫기':>5} {'열기':>5}  비고")

    n_success = 0
    for ep in np.unique(ep_idx):
        m = ep_idx == ep
        a, r, d = action[m], reward[m], done[m]
        success = r[-1] > 0
        n_success += success
        idle = float(np.mean(np.abs(a[:, :3]).max(axis=1) < 1e-6))
        notes = []
        if not d[-1] or d[:-1].any():
            notes.append("⚠️done 형식")
        if r[:-1].any():
            notes.append("⚠️reward가 중간에 있음")
        if idle > IDLE_WARN:
            notes.append("⚠️가만히 있는 시간 많음")
        close = open_ = 0
        if has_gripper:
            g = a[:, 3].round().astype(int)
            starts = np.flatnonzero(np.diff(np.r_[1, g]) != 0)  # 명령이 바뀐 지점
            close = int(np.sum(g[starts] == 0))
            open_ = int(np.sum(g[starts] == 2))
        print(
            f"{ep:>4} {len(a) / ds.fps:>6.1f}s {'성공' if success else '실패':>6} {idle:>8.0%} {close:>5} {open_:>5}  "
            + " ".join(notes)
        )

    n = ds.num_episodes
    print(f"\n성공 {n_success} / 실패 {n - n_success}  (성공률 {n_success / max(n, 1):.0%})")
    print("액션 범위 (dx, dy, dz): min " + str(action[:, :3].min(axis=0).round(2)) + "  max " + str(action[:, :3].max(axis=0).round(2)))


if __name__ == "__main__":
    main()
