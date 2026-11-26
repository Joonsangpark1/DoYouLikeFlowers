"""Observer: 둘러보기로 꽃 배치 판단 (11-25). VLA를 안 쓰므로 꽃병은 도면 위치(반지름 250)이고 세 꽃이 한 화면에 안 들어옴 →
시작 자세에서 어깨 회전만 LOOK_PANS(기본 −15°, 0°, +15° = 시작 자세 기준 상대각)로 돌려 손목 카메라 3장 → 사진마다 YOLO →
화면 가운데에 가장 가까운 꽃 = 그 방향 칸의 꽃. 어깨 회전 음수 = 로봇 왼쪽 = 1번 칸 (IK: 1번 칸 pan −23°, 3번 칸 +23°).
YOLO는 OpenCV DNN으로 ONNX 실행 (ultralytics·torch 불필요 → AI-G 보드에서도 같은 코드). 모델 models/flowers_v8n.onnx (YOLOv8n, 640, 클래스 rose/blue/sunflower)

함수:  detect(rgb) → [(cls, conf, x0,y0,x1,y1)],  layout_from_views([...]) → {"1": "sunflower", ...},  look_around(robot, names, cam) → (layout, 사진들)
단독 (WSL, 로봇+손목 카메라 연결):  python observer_look.py            # 둘러보고 배치 출력, 사진은 D:\\data\\flower\\look\\
오프라인 시험 (로봇 없이):          python observer_look.py --image a.jpg
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
CLASSES = ["rose", "blue", "sunflower"]
MODEL = os.environ.get("FLOWER_YOLO", str(HERE / "models/flowers_v8n.onnx"))
LOOK_PANS = [float(x) for x in os.environ.get("LOOK_PANS", "-15,0,15").split(",")]
_net = None


def _load():
    global _net
    if _net is None:
        _net = cv2.dnn.readNetFromONNX(MODEL)
    return _net


def detect(rgb: np.ndarray, conf_th: float = 0.35, iou_th: float = 0.5, size: int = 640):
    """YOLOv8 ONNX 출력 (1, 4+클래스수, N) 해석 + NMS. 반환 [(클래스, 점수, x0, y0, x1, y1)] (원본 픽셀)"""
    h, w = rgb.shape[:2]
    s = size / max(h, w)  # letterbox: 비율 유지 축소 + 오른쪽·아래 회색 채움 (ultralytics는 가운데 채움이지만 좌표만 맞추면 됨)
    nh, nw = int(round(h * s)), int(round(w * s))
    canvas = np.full((size, size, 3), 114, np.uint8)
    canvas[:nh, :nw] = cv2.resize(rgb, (nw, nh))
    blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0, (size, size), swapRB=False)  # 이미 RGB
    net = _load(); net.setInput(blob)
    out = net.forward()[0]  # (4+C, N)
    boxes, scores, cls = out[:4].T, out[4:].T.max(1), out[4:].T.argmax(1)
    keep = scores >= conf_th
    boxes, scores, cls = boxes[keep], scores[keep], cls[keep]
    xyxy = np.c_[boxes[:, 0] - boxes[:, 2] / 2, boxes[:, 1] - boxes[:, 3] / 2, boxes[:, 0] + boxes[:, 2] / 2, boxes[:, 1] + boxes[:, 3] / 2] / s
    res = []
    for c in range(len(CLASSES)):
        m = cls == c
        if not m.any():
            continue
        b = xyxy[m]; sc = scores[m]
        idx = cv2.dnn.NMSBoxes([[float(x0), float(y0), float(x1 - x0), float(y1 - y0)] for x0, y0, x1, y1 in b], sc.tolist(), conf_th, iou_th)
        for i in np.array(idx).reshape(-1):
            x0, y0, x1, y1 = np.clip(b[i], 0, [w, h, w, h])
            res.append((CLASSES[c], float(sc[i]), float(x0), float(y0), float(x1), float(y1)))
    return res


def center_flower(dets, w: int):
    """화면 가로 가운데에 가장 가까운 꽃 (클래스, 점수, 가운데에서 떨어진 비율)"""
    if not dets:
        return None
    c, s, x0, y0, x1, y1 = min(dets, key=lambda d: abs((d[2] + d[4]) / 2 - w / 2))
    return c, s, abs((x0 + x1) / 2 - w / 2) / w


PX_PER_DEG = float(os.environ.get("LOOK_PX_PER_DEG", 18.0))  # 11-25 실측: 어깨 15° 돌리면 같은 꽃이 약 274 px 이동 (손목 카메라가 꽃에 가까워 시차 포함)


def layout_from_views(views: list[tuple[float, list, int]]) -> dict[str, str | None]:
    """views = [(어깨 상대각, detect 결과, 화면 폭)].
    11-25 실물 둘러보기: 꽃이 카메라에 가까워 '사진마다 가운데 꽃' 규칙은 −15°에서 해바라기 대신 장미를 고름 → 바꿈:
    잡힌 꽃마다 방향각 ψ = 어깨 상대각 + (박스 가로 중심 − 화면 가운데)/PX_PER_DEG (음수 = 로봇 왼쪽),
    꽃 종류별 점수 가중 중앙값 → 왼쪽부터 1·2·3번 칸. 안 잡힌 꽃은 남은 칸."""
    psi = {}
    for pan, dets, w in views:
        for c, s, x0, y0, x1, y1 in dets:
            psi.setdefault(c, []).append((pan + ((x0 + x1) / 2 - w / 2) / PX_PER_DEG, s))
    med = {}
    for c, v in psi.items():
        v = sorted(v); ws = np.cumsum([s for _, s in v]); med[c] = v[int(np.searchsorted(ws, ws[-1] / 2))][0]
    order = sorted(med, key=med.get)
    layout = {s: None for s in ("1", "2", "3")}
    if len(order) == 3:
        for i, c in enumerate(order):
            layout[str(i + 1)] = c
    elif len(order) == 2:  # 하나 안 보임: 두 꽃 방향각으로 칸 추정 (칸 사이 약 20°)
        a_, b_ = order
        if med[b_] - med[a_] > 30:
            layout["1"], layout["3"] = a_, b_
        elif (med[a_] + med[b_]) / 2 < 0:
            layout["1"], layout["2"] = a_, b_
        else:
            layout["2"], layout["3"] = a_, b_
        layout[[k for k, v in layout.items() if v is None][0]] = [f for f in CLASSES if f not in order][0]
    layout["_psi_deg"] = {c: round(float(m), 1) for c, m in med.items()}
    return layout


def look_around(robot, names, cam, settle_s: float = 0.6, save_dir: Path | None = None):
    """시작 자세에서 어깨만 LOOK_PANS 상대각으로 돌려 3장 → 배치. 끝나면 원래 어깨 각도로."""
    import record_prior as RP
    q0 = RP.read_q(robot, names)
    views, shots = [], []
    for dp in LOOK_PANS:
        RP.move_smooth(robot, {**dict(zip(names, q0.tolist())), "shoulder_pan": float(q0[0] + dp)})
        time.sleep(settle_s)
        rgb = cam.read_fresh() if hasattr(cam, "read_fresh") else cam.read_latest()
        d = detect(rgb)
        views.append((dp, d, rgb.shape[1])); shots.append((dp, rgb, d))
    RP.move_smooth(robot, dict(zip(names, q0.tolist())))
    layout = layout_from_views(views)
    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        tiles = [draw(rgb, d, f"pan {dp:+.0f}") for dp, rgb, d in shots]
        stamp = time.strftime('%m%d_%H%M%S')
        cv2.imwrite(str(save_dir / f"look_{stamp}.jpg"), np.hstack([cv2.resize(t, (320, 240)) for t in tiles]))
        for dp, rgb, _ in shots:  # 원본도 저장 (규칙 다듬기용)
            cv2.imwrite(str(save_dir / f"look_{stamp}_pan{dp:+.0f}.jpg"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return layout, shots


def draw(rgb, dets, title=""):
    col = {"rose": (160, 60, 255), "blue": (255, 120, 40), "sunflower": (0, 210, 255)}
    v = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    for c, s, x0, y0, x1, y1 in dets:
        cv2.rectangle(v, (int(x0), int(y0)), (int(x1), int(y1)), col[c], 3)
        cv2.putText(v, f"{c} {s:.2f}", (int(x0), int(y0) + 22), 0, 0.7, col[c], 2)
    cv2.line(v, (v.shape[1] // 2, 0), (v.shape[1] // 2, v.shape[0]), (255, 255, 255), 1)
    cv2.putText(v, title, (8, v.shape[0] - 12), 0, 0.8, (255, 255, 255), 2)
    return v


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", nargs="*", help="로봇 없이 사진에 YOLO만")
    a = ap.parse_args()
    if a.image:
        for p in a.image:
            rgb = cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2RGB)
            d = detect(rgb)
            print(p, [(c, round(s, 2), int((x0 + x1) / 2)) for c, s, x0, y0, x1, y1 in d])
            cv2.imwrite(str(Path(p).with_suffix(".det.jpg")), draw(rgb, d))
    else:
        import json
        import record_prior as RP
        from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
        from net_camera import NetCamera
        rcfg = json.loads((HERE / "configs/flower_hil.json").read_text())["env"]["robot"]
        robot = SO101Follower(SO101FollowerConfig(port=RP.by_id("/dev/serial/by-id/usb-1a86_*", rcfg["port"]), id=rcfg["id"],
                                                  max_relative_target=10.0, disable_torque_on_disconnect=False))
        robot.connect(); names = list(robot.bus.motors)
        cam = NetCamera(port=5558); cam.connect()
        start = json.loads((RP.SMOLVLA_CODE / "start_pose_vla_trial4.json").read_text())
        if input("시작 자세로 이동 후 둘러보기 (어깨 ±15°). 진행? [y/N] ").lower() == "y":
            RP.move_smooth(robot, start)
            layout, _ = look_around(robot, names, cam, save_dir=Path("/mnt/d/data/flower/look"))
            print("배치:", layout, " (사진: D:\\data\\flower\\look\\)")
        RP.hold_here(robot); robot.disconnect(); cam.disconnect()
