"""
WSL + usbipd 환경용 카메라 유틸 (camera_preview.py, record_dataset.py 공용).

UsbipOpenCVCamera
  lerobot의 OpenCVCamera.connect()는 기본 설정으로 연 뒤 set(FOURCC/WIDTH/...)을
  호출하는데, OpenCV V4L2 백엔드는 이 set 때마다 내부적으로 장치를 닫았다 다시 연다.
  usbip 환경에서는 이 재오픈이 실패해 fd가 -1이 되면서 'VIDIOC_QBUF: Bad file
  descriptor' + "failed to set capture_width"가 나는 경우가 있었다 (v4l2-ctl로는 640x480
  MJPG 스트리밍 정상). 그래서 설정값을 VideoCapture를 여는 시점에 open params로 한 번에
  넘기고, 연 뒤에는 set을 호출하지 않는다.

  또 WSL+usbipd로 붙인 웹캠은 기본 포맷(YUYV, 비압축)으로 열면 usbip 가상 버스 대역폭을
  못 버티므로 fourcc=MJPG + 640x480 조합을 쓴다 (1280x720은 MJPG 협상 실패 실측).

MjpegServer
  WSL에서 Rerun 네이티브 창이 안 뜨고, Rerun 웹 뷰어는 브라우저 WebGPU 버퍼 한도로
  크래시가 나서, 브라우저 GPU를 안 쓰는 MJPEG over HTTP로 미리보기를 띄운다.
  Windows 브라우저에서 http://localhost:<port> 로 연다.
"""
from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

from lerobot.cameras.opencv import OpenCVCamera


class UsbipOpenCVCamera(OpenCVCamera):
    """open 이후 set()으로 재설정하지 않고, 열 때 open params로 포맷을 한 번에 지정하는 OpenCVCamera.

    MJPG일 때는 usbip에서 중간 데이터가 빠진 프레임('Corrupt JPEG data: premature end of data
    segment')이 섞여 들어온다. 끝 마커(FFD9)는 붙어 있어서 마커 검사로는 못 거르고, OpenCV는 이런
    프레임도 아래쪽이 회색으로 깨진 이미지로 그냥 반환한다. 그래서 CONVERT_RGB=0으로 압축된 원본
    바이트를 받아 simplejpeg(strict=True: libjpeg 경고를 예외로 올림)로 직접 디코딩하고, 실패한
    프레임은 버린다. 버린 개수는 corrupt_frames에 누적. (pip install simplejpeg)
    """

    MAX_CORRUPT_RETRIES = 5
    WARMUP_GRACE_S = 5

    corrupt_frames = 0
    good_frames = 0

    def connect(self, warmup: bool = True) -> None:
        cv2.setNumThreads(1)

        params = []
        self._raw_mjpeg = self.config.fourcc == "MJPG"
        if self.config.fourcc is not None:
            params += [cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.config.fourcc)]
        if self._raw_mjpeg:
            params += [cv2.CAP_PROP_CONVERT_RGB, 0]
        if self.capture_width is not None and self.capture_height is not None:
            params += [cv2.CAP_PROP_FRAME_WIDTH, self.capture_width, cv2.CAP_PROP_FRAME_HEIGHT, self.capture_height]
        if self.fps is not None:
            params += [cv2.CAP_PROP_FPS, self.fps]

        self.videocapture = cv2.VideoCapture(self.index_or_path, cv2.CAP_V4L2, params)
        if not self.videocapture.isOpened():
            self.videocapture.release()
            self.videocapture = None
            raise ConnectionError(f"Failed to open {self}.")

        try:
            actual_w = int(round(self.videocapture.get(cv2.CAP_PROP_FRAME_WIDTH)))
            actual_h = int(round(self.videocapture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            if (actual_w, actual_h) != (self.capture_width, self.capture_height):
                raise RuntimeError(
                    f"{self} opened at {actual_w}x{actual_h}, expected {self.capture_width}x{self.capture_height}."
                )

            self._start_read_thread()

            if warmup and self.warmup_s > 0:
                # 한동안 안 쓰던 카메라는 첫 장 뒤 1초 넘게 멈췄다가 정상 속도로 돌아온다 (2026-11-15 실측,
                # 5회 중 첫 번째만). 원본처럼 warmup_s(1초) 타임아웃 한 번에 죽지 않고 WARMUP_GRACE_S까지 기다린다.
                start_time = time.time()
                while time.time() - start_time < self.warmup_s + self.WARMUP_GRACE_S:
                    try:
                        self.async_read(timeout_ms=self.warmup_s * 1000)
                    except TimeoutError:
                        continue
                    if time.time() - start_time >= self.warmup_s:
                        break
                    time.sleep(0.1)
                with self.frame_lock:
                    if self.latest_frame is None:
                        raise ConnectionError(f"{self} failed to capture frames during warmup.")
        except BaseException:
            self._cleanup_resources()
            self._reset_connection_settings()
            raise

    def _read_from_hardware(self) -> np.ndarray:
        if not self._raw_mjpeg:
            return super()._read_from_hardware()

        import simplejpeg

        for _ in range(self.MAX_CORRUPT_RETRIES):
            frame = super()._read_from_hardware()
            if frame.ndim == 3:
                # 이 OpenCV 빌드가 raw 모드를 무시하고 이미 디코딩된 BGR을 준 경우: 검사 불가, 그대로 사용
                if not getattr(self, "_mode_reported", False):
                    print(f"[{self}] ⚠️ raw MJPEG 모드 미지원 -> 손상 프레임 검사 비활성")
                    self._mode_reported = True
                self.good_frames += 1
                return frame
            if not getattr(self, "_mode_reported", False):
                print(f"[{self}] raw MJPEG 모드 -> 손상 프레임 검사 활성")
                self._mode_reported = True

            data = frame.reshape(-1)
            end = len(data)
            while end > 0 and data[end - 1] == 0:  # 버퍼 뒤쪽 0 패딩 제거
                end -= 1
            try:
                decoded = simplejpeg.decode_jpeg(data[:end].tobytes(), colorspace="BGR", strict=True)
                self.good_frames += 1
                return decoded
            except ValueError:
                self.corrupt_frames += 1

        raise RuntimeError(f"{self} {self.MAX_CORRUPT_RETRIES}프레임 연속 손상 (usbip 대역폭 부족 의심)")


class MjpegServer:
    """update()로 넣은 최신 프레임(RGB)을 MJPEG 스트림으로 서빙한다. 데몬 스레드라 별도 종료 불필요."""

    def __init__(self, port: int = 8080, fps: int = 30):
        self.port = port
        self._interval = 1 / fps
        self._jpeg: bytes | None = None
        self._lock = threading.Lock()

        server_self = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                # 스트림 URL을 주소창에 직접 열면 표시 안 하는 브라우저가 있어서, /는 <img>로 감싼 페이지를 준다
                if self.path != "/stream":
                    page = b"<html><body style='margin:0;background:#111'><img src='/stream' style='width:100%'></body></html>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(page)))
                    self.end_headers()
                    self.wfile.write(page)
                    return

                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    while True:
                        with server_self._lock:
                            jpg = server_self._jpeg
                        if jpg is not None:
                            self.wfile.write(
                                b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                + str(len(jpg)).encode()
                                + b"\r\n\r\n"
                                + jpg
                                + b"\r\n"
                            )
                        time.sleep(server_self._interval)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # 브라우저 탭을 닫음

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def update(self, frame_rgb: np.ndarray) -> None:
        ok, jpg = cv2.imencode(".jpg", cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR))
        if ok:
            with self._lock:
                self._jpeg = jpg.tobytes()
