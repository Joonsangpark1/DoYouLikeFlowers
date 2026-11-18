"""
record_dataset.py로 녹화한 데이터셋의 모터 값 점검.

에피소드별로 출력:
  - 추종 오차 |action - observation.state| (재생 때 모터가 시연 궤적을 얼마나 잘 따라갔는지)
    평균이 크면 모터가 못 따라간 것 (너무 빠른 시연 / 중력 부하 / 무언가에 막힘)
  - 프레임당 최대 action 변화량 (시연 궤적에 튀는 값이 있는지)
  - 시작 자세가 에피소드끼리 일정한지, 그리퍼가 고정돼 있는지
matplotlib이 있으면 에피소드별 action/state 그래프를 dataset_check/ 에 PNG로 저장.

사용 예:
  python check_dataset.py --repo-id local/flower_reach
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from lerobot.datasets import LeRobotDataset

TRACK_WARN_DEG = 5.0  # 평균 추종 오차가 이보다 크면 경고
JUMP_WARN_DEG = 5.0  # 한 프레임 사이 action 변화가 이보다 크면 경고 (30fps에서 150 deg/s)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--root", type=Path, default=None, help="기본: ~/lerobot_data/<repo-id>")
    parser.add_argument("--plot-dir", type=Path, default=Path(__file__).parent / "dataset_check")
    args = parser.parse_args()

    root = args.root or Path.home() / "lerobot_data" / args.repo_id
    ds = LeRobotDataset(args.repo_id, root=root)
    names = [n.removesuffix(".pos") for n in ds.features["action"]["names"]]
    tasks = list(ds.meta.tasks.index)

    data = ds.hf_dataset.select_columns(["action", "observation.state", "episode_index", "task_index"])
    data = data.with_format("numpy")
    action = np.stack(data["action"])
    state = np.stack(data["observation.state"])
    ep_idx = np.asarray(data["episode_index"])
    task_idx = np.asarray(data["task_index"])

    print(f"{args.repo_id}: 에피소드 {ds.num_episodes}개, {len(action)} frames, {ds.fps} fps")
    print(f"관절 순서: {names}\n")

    starts = []
    for ep in np.unique(ep_idx):
        m = ep_idx == ep
        a, s = action[m], state[m]
        task = tasks[int(task_idx[m][0])]
        err = np.abs(a - s)
        jump = np.abs(np.diff(a, axis=0)).max(axis=0) if len(a) > 1 else np.zeros(len(names))
        starts.append(s[0])

        print(f"[ep {ep}] {len(a)} frames ({len(a) / ds.fps:.1f}s)  task: {task}")
        print(f"   {'joint':<14}{'start':>8}{'end':>8}{'min':>8}{'max':>8}{'err avg':>9}{'err max':>9}{'jump':>7}")
        for j, n in enumerate(names):
            flag = ""
            if err[:, j].mean() > TRACK_WARN_DEG:
                flag += " ⚠️추종"
            if jump[j] > JUMP_WARN_DEG:
                flag += " ⚠️튐"
            print(
                f"   {n:<14}{s[0, j]:8.1f}{s[-1, j]:8.1f}{s[:, j].min():8.1f}{s[:, j].max():8.1f}"
                f"{err[:, j].mean():9.2f}{err[:, j].max():9.2f}{jump[j]:7.2f}{flag}"
            )
        if "gripper" in names:
            g = names.index("gripper")
            if np.ptp(a[:, g]) > 1e-3:
                print(f"   ⚠️ 그리퍼 action이 고정이 아님 (범위 {np.ptp(a[:, g]):.2f})")

    starts = np.stack(starts)
    print("\n시작 자세 에피소드 간 표준편차 (작을수록 시작 자세가 일정):")
    print("   " + "  ".join(f"{n}={v:.2f}" for n, v in zip(names, starts.std(axis=0))))

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib 없음 -> 그래프 생략. pip install matplotlib)")
        return

    args.plot_dir.mkdir(parents=True, exist_ok=True)
    t_all = np.arange(len(action)) / ds.fps
    for ep in np.unique(ep_idx):
        m = ep_idx == ep
        t = t_all[m] - t_all[m][0]
        fig, axes = plt.subplots(len(names), 1, figsize=(8, 2 * len(names)), sharex=True)
        for j, (ax, n) in enumerate(zip(axes, names)):
            ax.plot(t, action[m][:, j], label="action (replay target)")
            ax.plot(t, state[m][:, j], label="observation.state", alpha=0.8)
            ax.set_ylabel(n)
        axes[0].legend(loc="upper right", fontsize=8)
        axes[0].set_title(f"ep {ep}: {tasks[int(task_idx[m][0])]}")
        axes[-1].set_xlabel("time (s)")
        fig.tight_layout()
        fig.savefig(args.plot_dir / f"ep{ep:03d}.png", dpi=80)
        plt.close(fig)
    print(f"\n그래프 저장: {args.plot_dir}")


if __name__ == "__main__":
    main()
