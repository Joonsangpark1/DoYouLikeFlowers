"""카메라 2대 미리보기 (11-23): 손목(5558) | 고정 C270(5559) 나란히 → 브라우저 http://localhost:8081
꽃 배치·카메라 위치 잡을 때용. 녹화(record_prior.py) 전에 꼭 끄기 (같은 포트를 씀). Ctrl+C로 끝."""
import time

import cv2
import numpy as np

from net_camera import NetCamera
from usbip_camera import MjpegServer


def main():
    wrist, front = NetCamera(port=5558, width=640, height=480), NetCamera(port=5559, width=640, height=480)
    mjpeg = MjpegServer(port=8081, fps=15)
    wrist.connect()
    front.connect()
    print("미리보기: http://localhost:8081  (왼쪽 손목 / 오른쪽 고정)", flush=True)
    try:
        while True:
            a, b = wrist.read_latest(max_age_ms=2000), front.read_latest(max_age_ms=2000)
            img = np.hstack([a, b])
            cv2.putText(img, "wrist", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(img, "front C270", (650, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            mjpeg.update(img)
            time.sleep(1 / 15)
    except KeyboardInterrupt:
        pass
    finally:
        wrist.disconnect()
        front.disconnect()


if __name__ == "__main__":
    main()
