"""고정 카메라(C270) 미리보기 (11-22). 설치 위치 잡을 때 화면 확인용.

Windows: python camera_sender_windows.py --find c270 --port 5559 --exposure -5
WSL:     python view_c270.py   → Windows 브라우저 http://localhost:8081
5초마다 /mnt/d/data/flower/c270_view/latest.jpg 저장. Ctrl+C로 끝.
"""

import time
from pathlib import Path

import cv2

from net_camera import NetCamera
from usbip_camera import MjpegServer

OUT = Path("/mnt/d/data/flower/c270_view")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cam = NetCamera(port=5559, width=640, height=480)
    mjpeg = MjpegServer(port=8081, fps=15)
    cam.connect()
    print("미리보기: http://localhost:8081", flush=True)
    last = 0.0
    try:
        while True:
            img = cam.read_latest(max_age_ms=1000)
            mjpeg.update(img)
            if time.time() - last > 5:
                cv2.imwrite(str(OUT / "latest.jpg"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
                last = time.time()
            time.sleep(1 / 15)
    except KeyboardInterrupt:
        pass
    finally:
        cam.disconnect()


if __name__ == "__main__":
    main()
