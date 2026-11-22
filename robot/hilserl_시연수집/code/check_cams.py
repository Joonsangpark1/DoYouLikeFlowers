"""녹화 전 카메라 확인 (11-22): 손목 5558, 고정 5559 각 3초 프레임 수 + 사진 저장."""
import sys
import time
import cv2
from net_camera import NetCamera

WANT = sys.argv[1:] or ["wrist", "front"]  # 예: python check_cams.py wrist
for name, port in [x for x in (("wrist", 5558), ("front", 5559)) if x[0] in WANT]:
    cam = NetCamera(port=port, width=640, height=480)
    cam.connect()
    n, t0, last = 0, time.time(), None
    while time.time() - t0 < 3:
        img = cam.read_latest(max_age_ms=1000)
        if img is not last:
            n, last = n + 1, img
        time.sleep(0.005)
    cv2.imwrite(f"/mnt/d/data/flower/c270_view/check_{name}.jpg", cv2.cvtColor(last, cv2.COLOR_RGB2BGR))
    print(f"{name} ({port}): {n / 3:.1f} fps")
    cam.disconnect()
