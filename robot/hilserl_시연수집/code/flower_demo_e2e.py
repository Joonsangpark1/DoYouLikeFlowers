"""꽃꽂이 시연 end-to-end (11-27): 학습기·사람 버튼 없이 학습된 뽑기 정책으로 처음부터 끝까지.

한 송이 = 시작 자세 → 둘러보기(YOLO, 어깨 −15/0/+15°)로 배치 → 그 칸으로 IK 접근(줄기 3 cm 앞, 칸 2·3은 2 cm)
        → 뽑기 정책(손목·정면 사진 + 관절 → [dx, dy, dz, 그리퍼], 0.1 s마다, 최대 20 s, 줄기 주변 상자 안)
        → '뽑음' = 시작보다 8.5 cm 이상 들었고 그리퍼를 닫는 중(명령 ≥ 90)이 2스텝 연속
        → IK로 통에 넣기(칸 반대로 5 cm → 올라가며 통 쪽 → 통 위 12 cm → 10 cm 내려 놓기 → 올라옴)
        못 뽑으면 그리퍼 열고 빠진 뒤 다시 (--max-retry)
접근·관측·통 넣기는 flower_pick_actor.PickEnv 메서드를 그대로 씀 (11-27 혼자 81% 나온 그 코드). 정책만 학습기 대신 이 파일이 직접 실행.

주의: 그리퍼 값으로는 줄기를 쥐었는지 빈손인지 구분 안 됨 → 빈손으로 들어 올려도 통에 넣기를 함. --pad 면 1(꾹) 성공 / 2(꾹) 실패로 사람이 바로잡을 수 있음

사용 (WSL, 송신기 켜 둔 상태, 학습기 필요 없음):
  python flower_demo_e2e.py                                  # rose, blue, sunflower 순서로 한 바퀴, 시작 전에 Enter
  python flower_demo_e2e.py --flowers sunflower,rose --rounds 3
  python flower_demo_e2e.py --layout sunflower,rose,blue     # 둘러보기 생략 (1,2,3번 칸 꽃)
  python flower_demo_e2e.py --pad                            # 게임패드: 1 꾹 성공 / 2 꾹 실패 / SELECT 멈춤
미리보기 http://localhost:8080
"""
# (from __future__ import annotations 쓰면 lerobot parser.wrap 이 설정 타입을 못 읽음)

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("NO_LEARNER", "1")
import flower_pick_actor as FPA  # noqa: E402  (torch 스레드 고정·경로·상수·PickEnv)
import torch  # noqa: E402

RP = FPA.RP
HERE = FPA.HERE
_REPO_CKPT = HERE.parent / "policies/pull_13769/pretrained_model"  # 저장소에 같이 올린 정책 (11-27, 혼자 81%)
CKPT = Path(os.environ.get("FLOWER_POLICY", _REPO_CKPT if _REPO_CKPT.exists() else "/mnt/d/data/flower/policies/pull_13769/pretrained_model"))
LOG = Path.home() / "lerobot_data" / "parkjoonsang" / "flower_demo_episodes.jsonl"


class Policy:
    """학습기 없이 체크포인트를 바로 실행. 기본은 학습 때처럼 확률적 샘플(select_action), --deterministic 이면 tanh(평균)·그리퍼 argmax"""

    def __init__(self, ckpt: Path, deterministic: bool):
        from lerobot.configs import parser
        from lerobot.policies import make_policy, make_pre_post_processors
        from lerobot.rl.train_rl import TrainRLServerPipelineConfig
        from safetensors.torch import load_file
        holder = {}
        argv = sys.argv
        sys.argv = [argv[0], "--config_path", str(HERE / "configs/flower_pull2_train.json"), "--policy.device=cpu",
                    "--policy.storage_device=cpu", f"--output_dir=/tmp/flower_demo_{int(time.time())}"]

        @parser.wrap()
        def _build(cfg: TrainRLServerPipelineConfig):
            cfg.validate()
            holder["policy"] = make_policy(cfg=cfg.policy, env_cfg=cfg.env)
            holder["pre"], _ = make_pre_post_processors(policy_cfg=cfg.policy, dataset_stats=cfg.policy.dataset_stats)
        _build()
        sys.argv = argv
        self.policy, self.pre = holder["policy"].eval(), holder["pre"]
        self.policy.load_state_dict(load_file(ckpt / "model.safetensors"), strict=False)
        self.deterministic = deterministic
        step = json.loads((ckpt / "train_config.json").read_text()).get("job_name", "?")
        print(f"정책 {ckpt}  ({step}, {'결정적' if deterministic else '확률적 샘플'})")

    @torch.inference_mode()
    def act(self, obs: dict) -> np.ndarray:
        """→ [dx, dy, dz, 그리퍼(0 닫기 / 1 유지)]"""
        o = self.pre.process_observation(dict(obs))
        if self.deterministic:
            _, _, means = self.policy.actor(o, None)
            g = self.policy.discrete_critic(o, None).argmax(-1)
            return np.r_[torch.tanh(means)[0].numpy(), float(g[0])].astype(np.float32)
        return self.policy.select_action(batch=o)[0].numpy().astype(np.float32)


class Demo(FPA.PickEnv):
    def __init__(self, a):  # PickEnv.__init__ 대신: 게임패드·학습기 없이 로봇·카메라·IK만
        raw = json.loads((HERE / "configs/flower_hil.json").read_text())
        rcfg, ik = raw["env"]["robot"], raw["env"]["processor"]["inverse_kinematics"]
        self.a = a
        self.layout = [s.strip() for s in (a.layout or "sunflower,rose,blue").split(",")]
        self.pad = None
        if a.pad:
            self.pad = FPA.RemoteGamepad(FPA.RemoteGamepadConfig(port=raw["env"]["teleop"]["port"], deadzone=raw["env"]["teleop"]["deadzone"],
                                                                  always_intervene=True))
            self.pad.connect()
        self.wrist = FPA.NetCamera(port=5558); self.wrist.connect()
        self.front = FPA.NetCamera(port=5559, wait_connect_s=60); self.front.connect()
        port = RP.by_id("/dev/serial/by-id/usb-1a86_*", rcfg["port"])
        self.robot = FPA.SO101Follower(FPA.SO101FollowerConfig(port=port, id=rcfg["id"], max_relative_target=10.0, disable_torque_on_disconnect=False))
        self.robot.connect()
        self.names = list(self.robot.bus.motors)
        self.ctrl = FPA.WristEEController(str(HERE / ik["urdf_path"]), ik["target_frame_name"], self.names,
                                          xyz_step=0.008, roll_step=6.0, grip_step=10.0, bounds=ik.get("end_effector_bounds"))
        self.slot_poses = json.loads((HERE / "stereo/slot_poses.json").read_text())["slots"]
        self.fixed = json.loads((HERE / "configs/slot_targets.json").read_text())
        self.calibrated, self.rig = False, None
        from scripted_pick import ScriptedPicker
        self.picker = ScriptedPicker(self.robot, self.names)
        self._slot_u, self.holding, self.flower = None, False, None
        self.preview = FPA.MjpegServer(port=8080, fps=15)
        threading.Thread(target=self._preview_loop, daemon=True).start()
        self.policy = Policy(Path(a.policy), a.deterministic)

    def _stop_requested(self) -> bool:
        return self.pad is not None and self.pad.pop_pressed("back")

    def look(self):
        from observer_look import look_around
        RP.set_status("LOOK AROUND (YOLO)", RP.YELLOW)
        lay, _ = look_around(self.robot, self.names, self.wrist, save_dir=Path("/mnt/d/data/flower/look"))
        if all(lay.get(k) for k in "123"):
            self.layout = [lay["1"], lay["2"], lay["3"]]
            print(f"   배치(YOLO): {'-'.join(f[0].upper() for f in self.layout)}  각도 {lay.get('_psi_deg')}")
        else:
            print(f"   배치 판단 실패 {lay} → 이전 배치 {self.layout}")

    def pull(self) -> dict:
        """정책으로 뽑기. flower_pick_actor.step_transition 의 행동·간격·상자·그리퍼 처리 그대로 (개입·학습 저장만 없음)"""
        q0 = RP.hold_here(self.robot)
        self.ctrl.reset_from(q0); self.z0 = self._ee_z(q0)
        p0 = self.ctrl.p_cmd
        self.ctrl.bounds = {"min": [p0[0] - FPA.BOX_XY, p0[1] - FPA.BOX_XY, p0[2] - FPA.BOX_DOWN],
                            "max": [p0[0] + FPA.BOX_XY, p0[1] + FPA.BOX_XY, p0[2] + FPA.BOX_UP]}
        t0 = time.perf_counter(); obs = self._obs(); t_obs = time.perf_counter()
        n, streak, lift, result = 0, 0, 0.0, "timeout"
        while time.perf_counter() - t0 < self.a.control_time_s:
            pa = self.policy.act(obs)
            a = np.array([*np.clip(pa[:3], -1, 1), 0.0, float(np.clip(np.rint(pa[3]), 0, 2))], np.float32)
            if int(a[4]) == FPA.GRIPPER_OPEN:
                a[4] = FPA.GRIPPER_STAY
            q = self.ctrl.step(a)
            if q[5] < FPA.PICK_OPEN:
                q[5] = self.ctrl.q_cmd[5] = FPA.PICK_OPEN
            self.robot.bus.sync_write("Goal_Position", dict(zip(self.names, q, strict=True)))
            n += 1
            time.sleep(max(0.0, max(t_obs + FPA.STEP_S, time.perf_counter() + FPA.MIN_OBS_DELAY) - time.perf_counter()))
            obs = self._obs(); t_obs = time.perf_counter()
            qm = obs[FPA.STATE_KEY][0].numpy()
            lift = self._ee_z(qm) - self.z0
            streak = streak + 1 if (lift >= FPA.LIFT_M and self.ctrl.q_cmd[5] >= FPA.CLOSE_CMD) else 0
            el = time.perf_counter() - t0
            RP.set_status(f"POLICY [{self.flower}] {el:4.1f}/{self.a.control_time_s:.0f}s grip {qm[5]:.0f}/{self.ctrl.q_cmd[5]:.0f} lift {lift * 100:.1f}cm",
                          RP.GREEN)
            if streak >= 2:
                result = "pulled"; break
            if self.pad is not None:
                if RP.held(self.pad, "y") and lift >= FPA.PULL_SUCCESS_M:
                    result = "pulled(button)"; break
                if RP.held(self.pad, "b"):
                    result = "failure(button)"; break
                if self._stop_requested():
                    raise KeyboardInterrupt
        return {"result": result, "steps": n, "seconds": round(time.perf_counter() - t0, 1), "lift_cm": round(lift * 100, 1),
                "hz": round(n / max(1e-6, time.perf_counter() - t0), 1)}

    def pick_flower(self, flower: str, look: bool) -> dict:
        self.flower = flower
        for attempt in range(1, self.a.max_retry + 2):
            if self._slot_u is not None:  # 지난 시도 칸에서 빠지기
                self.reset_retreat()
            self.picker.grip(FPA.PICK_OPEN); self.picker.home()
            if look:
                self.look()
            if flower not in self.layout:
                return {"flower": flower, "result": "not_found", "layout": self.layout}
            slot = self.layout.index(flower) + 1
            print(f"[{flower}] 칸{slot} 시도 {attempt}  전압 {RP.read_volt(self.robot)} V")
            RP.set_status(f"APPROACH {flower} slot {slot}", RP.YELLOW)
            self._approach(slot)
            r = self.pull()
            r.update(flower=flower, slot=slot, attempt=attempt, time=time.strftime("%Y-%m-%d %H:%M:%S"), policy=str(self.a.policy))
            print(f"   정책 {r}")
            if r["result"].startswith("pulled"):
                self._place_scripted()
                self._slot_u = None
                r["placed"] = not self.holding
                self.picker.home()
            else:
                self.picker.grip(FPA.PICK_OPEN)
            LOG.parent.mkdir(parents=True, exist_ok=True)
            with LOG.open("a") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            if r["result"].startswith("pulled"):
                return r
            look = False  # 다시 할 땐 배치 그대로
        self.reset_retreat()
        return r

    def reset_retreat(self):
        """칸 방향 반대로 8 cm 빠진 뒤 시작 자세 (flower_pick_actor.reset_transition 앞부분)"""
        if self._slot_u is not None:
            try:
                p_stem, u, pitch = self._slot_u
                p, _ = self.ctrl.ik.pose(self._q())
                self.picker.line_to(np.array([p[0], p[1], max(p[2], p_stem[2])]) - u * 0.08, pitch)
            except Exception as e:
                print("   빠지기 실패, 바로 시작 자세로:", e)
            self._slot_u = None
        self.picker.grip(FPA.PICK_OPEN); self.picker.home()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flowers", default="rose,blue,sunflower", help="뽑을 순서 (rose / blue / sunflower)")
    ap.add_argument("--rounds", type=int, default=1, help="몇 바퀴 (바퀴 사이에 꽃 다시 꽂고 Enter)")
    ap.add_argument("--layout", help="둘러보기 대신 배치 직접 (1,2,3번 칸 꽃 이름)")
    ap.add_argument("--look-each", action="store_true", help="꽃마다 둘러보기 (기본: 바퀴마다 처음 한 번)")
    ap.add_argument("--max-retry", type=int, default=2)
    ap.add_argument("--control-time-s", type=float, default=FPA.CONTROL_TIME_S)
    ap.add_argument("--policy", default=str(CKPT), help="pretrained_model 폴더 (model.safetensors)")
    ap.add_argument("--deterministic", action="store_true", help="tanh(평균) (기본은 학습 때처럼 확률적 샘플)")
    ap.add_argument("--pad", action="store_true", help="게임패드로 1 꾹 성공 / 2 꾹 실패 / SELECT 멈춤")
    ap.add_argument("--no-wait", action="store_true", help="시작 전 Enter 안 기다림")
    a = ap.parse_args()
    demo = Demo(a)
    flowers = [s.strip() for s in a.flowers.split(",")]
    summary = []
    try:
        for rnd in range(1, a.rounds + 1):
            demo.picker.grip(FPA.PICK_OPEN); demo.picker.home()
            RP.set_status(f"READY round {rnd}/{a.rounds}  {'-'.join(flowers)}", RP.WHITE)
            if not a.no_wait:
                input(f"\n[{rnd}/{a.rounds}바퀴] 꽃을 꽃병에 꽂고 Enter ")
            for i, f in enumerate(flowers):
                r = demo.pick_flower(f, look=not a.layout and (i == 0 or a.look_each))
                summary.append(r)
        demo.picker.home()
    except KeyboardInterrupt:
        print("멈춤 (그 자리 유지)")
    finally:
        RP.hold_here(demo.robot)
        ok = sum(str(r.get("result", "")).startswith("pulled") for r in summary)
        print(f"\n결과: {ok}/{len(summary)} 송이 뽑아서 넣음")
        for r in summary:
            print(f"   {r.get('flower')}: {r.get('result')} (시도 {r.get('attempt')}, {r.get('seconds')} s, lift {r.get('lift_cm')} cm)")
        os._exit(0)


if __name__ == "__main__":
    main()
