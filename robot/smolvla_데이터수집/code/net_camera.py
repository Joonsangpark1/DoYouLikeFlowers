"""[WSL] Windows camera_sender_windows.py가 보내는 JPEG를 받는 카메라 (usbip 대신, 2026-11-17).

record_dataset.py가 쓰는 UsbipOpenCVCamera와 같은 부분만 맞춤:
  connect() / disconnect() / read_latest(max_age_ms) / async_read() / read()
  frame_lock, latest_frame, latest_timestamp, thread, corrupt_frames, good_frames, is_connected
프레임은 RGB (record_dataset.py가 ColorMode.RGB로 씀). 포트 5558에서 Windows 송신기 접속을 기다린다.
"""
from __future__ import annotations

import socket
import struct
import threading
import time

import numpy as np


class NetCamera:
    def __init__(self, port: int = 5558, width: int = 640, height: int = 480, wait_connect_s: float = 60.0):
        self.port, self.width, self.height, self.wait_connect_s = port, width, height, wait_connect_s
        self.frame_lock = threading.Lock()
        self.latest_frame: np.ndarray | None = None
        self.latest_timestamp: float | None = None
        self.thread: threading.Thread | None = None
        self.corrupt_frames = 0
        self.good_frames = 0
        self._new = threading.Event()
        self._running = False
        self._server: socket.socket | None = None

    def __str__(self):
        return f"NetCamera(:{self.port})"

    @property
    def is_connected(self) -> bool:
        return self._running

    def connect(self, warmup: bool = True) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", self.port))
        self._server.listen(1)
        self._running = True
        self.thread = threading.Thread(target=self._serve, name=f"{self}_read_loop", daemon=True)
        self.thread.start()
        print(f"[{self}] Windows camera_sender_windows.py 연결 대기 (포트 {self.port})", flush=True)
        deadline = time.time() + self.wait_connect_s
        while self.latest_frame is None:
            if time.time() > deadline:
                self.disconnect()
                raise ConnectionError(f"{self}: {self.wait_connect_s:.0f}초 동안 사진이 안 옴 "
                                      "(Windows에서 camera_sender_windows.py 켰는지 확인)")
            time.sleep(0.05)
        print(f"[{self}] 수신 OK", flush=True)

    def _recv_exact(self, conn: socket.socket, n: int) -> bytes | None:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = conn.recv(n - len(buf))
            except socket.timeout:
                if not self._running:
                    return None
                continue
            if not chunk:
                return None
            buf += chunk
        return bytes(buf)

    def _serve(self) -> None:
        import simplejpeg

        while self._running:
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            conn.settimeout(1.0)
            print(f"[{self}] Windows 송신기 연결됨", flush=True)
            with conn:
                while self._running:
                    head = self._recv_exact(conn, 4)
                    if head is None:
                        break
                    data = self._recv_exact(conn, struct.unpack(">I", head)[0])
                    if data is None:
                        break
                    try:
                        img = simplejpeg.decode_jpeg(data, colorspace="RGB", strict=True)
                    except ValueError:
                        self.corrupt_frames += 1
                        continue
                    if img.shape[:2] != (self.height, self.width):
                        self.corrupt_frames += 1
                        continue
                    with self.frame_lock:
                        self.latest_frame, self.latest_timestamp = img, time.perf_counter()
                    self.good_frames += 1
                    self._new.set()
            if self._running:
                print(f"[{self}] Windows 송신기 끊김 -> 다시 연결 대기", flush=True)

    def read_latest(self, max_age_ms: int = 500) -> np.ndarray:
        with self.frame_lock:
            frame, ts = self.latest_frame, self.latest_timestamp
        if frame is None or ts is None:
            raise RuntimeError(f"{self} 아직 받은 사진 없음")
        age = (time.perf_counter() - ts) * 1000
        if age > max_age_ms:
            raise TimeoutError(f"{self} 마지막 사진이 {age:.0f}ms 전 (최대 {max_age_ms}ms)")
        return frame

    def async_read(self, timeout_ms: float = 200) -> np.ndarray:
        self._new.clear()
        if not self._new.wait(timeout_ms / 1000):
            raise TimeoutError(f"{self} {timeout_ms}ms 동안 새 사진 없음")
        with self.frame_lock:
            return self.latest_frame

    def read(self) -> np.ndarray:
        return self.async_read(1000)

    def disconnect(self) -> None:
        self._running = False
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
