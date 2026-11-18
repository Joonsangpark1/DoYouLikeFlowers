"""
lerobot 공식 HIL-SERL 파이프라인(gym_manipulator / actor)에 끼워 넣는 플러그인 2개.
import만 하면 config의 "type"으로 쓸 수 있게 등록된다.

  "type": "usbip_camera"    WSL+usbipd용 카메라 (usbip_camera.UsbipOpenCVCamera)
                            + 브라우저 미리보기(preview_port)에 현재 상태 글자를 얹어서 보여줌
  "type": "remote_gamepad"  Windows에서 gamepad_sender.ps1이 보내는 게임패드 입력을 TCP로 받는 텔레오퍼레이터.
                            동작은 lerobot 공식 GamepadTeleop과 같음 (EE delta x/y/z + 그리퍼 0닫기/1유지/2열기,
                            RB=개입, Y=성공, A=실패, X=다시 찍기)

왜 직접 만들었나:
  - 공식 OpenCVCamera는 WSL+usbipd에서 'Bad file descriptor'로 실패 (smolvla 수집 때와 같은 문제)
  - 공식 GamepadTeleop은 pygame으로 패드를 직접 여는데, WSL 커널에는 Xbox 패드 드라이버(xpad)가 없어서
    usbipd로 넘겨도 안 보인다. 그래서 패드는 Windows에 그대로 두고 XInput으로 읽어 네트워크로 넘긴다.
    (Windows -> WSL은 localhost 포워딩으로 바로 연결됨. 미리보기 8080과 같은 원리)

나중에 HIL-SERL actor를 돌릴 때도 이 모듈을 import한 뒤 lerobot.rl.actor를 실행하면 같은 장치를 쓸 수 있다.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from lerobot.cameras import CameraConfig
from lerobot.cameras.opencv import OpenCVCameraConfig
from lerobot.teleoperators.config import TeleoperatorConfig
from lerobot.teleoperators.teleoperator import Teleoperator
from lerobot.teleoperators.utils import TeleopEvents

from usbip_camera import MjpegServer, UsbipOpenCVCamera

# ---------------------------------------------------------------------------
# 미리보기 상태 글자 (녹화 스크립트가 set_status로 바꾸면 카메라 스레드가 영상에 그려 넣음)
# ---------------------------------------------------------------------------
_status_lock = threading.Lock()
_status: tuple[str, tuple[int, int, int]] = ("", (255, 255, 255))

GREEN, RED, YELLOW, WHITE = (0, 200, 0), (0, 0, 255), (0, 220, 255), (255, 255, 255)  # BGR


def set_status(text: str, color: tuple[int, int, int] = WHITE) -> None:
    global _status
    with _status_lock:
        _status = (text, color)


def _draw_status(frame_bgr: np.ndarray) -> np.ndarray:
    with _status_lock:
        text, color = _status
    if not text:
        return frame_bgr
    out = frame_bgr.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], 34), (0, 0, 0), -1)
    cv2.putText(out, text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
    return out


# ---------------------------------------------------------------------------
# 카메라
# ---------------------------------------------------------------------------
@CameraConfig.register_subclass("usbip_camera")
@dataclass
class UsbipCameraConfig(OpenCVCameraConfig):
    preview_port: int | None = 8080  # None이면 미리보기 끔. 카메라가 여러 대면 포트를 다르게


class UsbipCamera(UsbipOpenCVCamera):
    """UsbipOpenCVCamera + 브라우저 미리보기 (읽기 스레드에서 프레임마다 갱신 -> 메인 루프가 멈춰 있어도 영상은 계속 보임)"""

    def __init__(self, config: UsbipCameraConfig):
        super().__init__(config)
        self._preview = MjpegServer(port=config.preview_port, fps=config.fps or 30) if config.preview_port else None

    def _read_from_hardware(self) -> np.ndarray:
        frame = super()._read_from_hardware()  # BGR (색 변환은 이후 단계에서)
        if self._preview is not None:
            self._preview.update_bgr(_draw_status(frame))
        return frame


# ---------------------------------------------------------------------------
# 게임패드 (Windows gamepad_sender.ps1 -> TCP -> 여기)
# ---------------------------------------------------------------------------
# XInput 버튼 비트 (gamepad_sender.ps1이 그대로 보냄)
BUTTONS = {
    "start": 0x0010,
    "back": 0x0020,
    "lb": 0x0100,
    "rb": 0x0200,
    "a": 0x1000,
    "b": 0x2000,
    "x": 0x4000,
    "y": 0x8000,
}

GRIPPER_CLOSE, GRIPPER_STAY, GRIPPER_OPEN = 0, 1, 2  # lerobot GamepadTeleop.GripperAction과 같은 값


@TeleoperatorConfig.register_subclass("remote_gamepad")
@dataclass
class RemoteGamepadConfig(TeleoperatorConfig):
    port: int = 5557  # gamepad_sender.ps1의 -Port와 같아야 함
    use_gripper: bool = True
    deadzone: float = 0.15  # 스틱을 놓았을 때 미세하게 흔들리는 값 무시
    # 축 방향이 반대로 움직이면 -1로 (gamepad_test.py로 확인)
    x_sign: float = 1.0  # 왼쪽 스틱 위/아래 -> EE x
    y_sign: float = 1.0  # 왼쪽 스틱 좌/우 -> EE y
    z_sign: float = 1.0  # 오른쪽 스틱 위/아래 -> EE z
    swap_gripper: bool = False  # RT/LT가 반대로 동작하면 true
    # True: RB를 안 눌러도 항상 사람이 조종 (시연 녹화용). False: RB를 누르는 동안만 개입 (actor 학습용)
    always_intervene: bool = False
    timeout_s: float = 0.5  # 이 시간 동안 입력이 안 오면 연결 끊김으로 보고 정지
    wait_connect_s: float = 120.0  # connect() 때 sender 연결을 기다리는 최대 시간


class RemoteGamepad(Teleoperator):
    config_class = RemoteGamepadConfig
    name = "remote_gamepad"

    def __init__(self, config: RemoteGamepadConfig):
        super().__init__(config)
        self.config = config
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {}
        self._last_rx = 0.0
        self._pressed: set[str] = set()  # 눌렀다가 아직 소비 안 된 버튼 (상승 에지)
        self._prev_buttons = 0
        self._server: socket.socket | None = None
        self._running = False

    # --- 수신 ---
    def _serve(self) -> None:
        while self._running:
            try:
                conn, addr = self._server.accept()
            except OSError:
                return
            print(f"[gamepad] sender 연결됨 {addr[0]}")
            buf = b""
            with conn:
                conn.settimeout(1.0)
                while self._running:
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    *lines, buf = buf.split(b"\n")
                    for line in lines:
                        if line.strip():
                            self._on_packet(json.loads(line))
            print("[gamepad] sender 연결 끊김 -> 정지. gamepad_sender.ps1이 켜져 있는지 확인")

    def _on_packet(self, pkt: dict) -> None:
        with self._lock:
            self._state = pkt
            self._last_rx = time.perf_counter()
            btn = int(pkt.get("btn", 0)) if pkt.get("pad", -1) >= 0 else 0
            rising = btn & ~self._prev_buttons
            for name, bit in BUTTONS.items():
                if rising & bit:
                    self._pressed.add(name)
            self._prev_buttons = btn

    def _live_state(self) -> dict[str, Any] | None:
        """최근 timeout_s 안에 받은 패드 상태. 연결 끊김/패드 없음이면 None."""
        with self._lock:
            if time.perf_counter() - self._last_rx > self.config.timeout_s:
                return None
            if self._state.get("pad", -1) < 0:
                return None
            return dict(self._state)

    # --- 녹화 스크립트용 ---
    def pop_pressed(self, name: str) -> bool:
        """name 버튼이 마지막 확인 이후 눌렸으면 True (한 번 누름 = 한 번만 True)."""
        with self._lock:
            if name in self._pressed:
                self._pressed.discard(name)
                return True
            return False

    def clear_pressed(self) -> None:
        with self._lock:
            self._pressed.clear()

    def is_live(self) -> bool:
        return self._live_state() is not None

    # --- Teleoperator 인터페이스 ---
    @property
    def action_features(self) -> dict:
        names = {"delta_x": 0, "delta_y": 1, "delta_z": 2}
        if self.config.use_gripper:
            names["gripper"] = 3
        return {"dtype": "float32", "shape": (len(names),), "names": names}

    @property
    def feedback_features(self) -> dict:
        return {}

    @property
    def is_connected(self) -> bool:
        return self._running

    def connect(self, calibrate: bool = True) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", self.config.port))
        self._server.listen(1)
        self._running = True
        threading.Thread(target=self._serve, daemon=True).start()

        print(f"[gamepad] 포트 {self.config.port}에서 대기 중 -> Windows에서 gamepad_sender.ps1 실행")
        deadline = time.perf_counter() + self.config.wait_connect_s
        while not self.is_live():
            if time.perf_counter() > deadline:
                self.disconnect()
                raise ConnectionError("게임패드 입력이 안 들어옵니다 (sender 실행/패드 연결 확인)")
            time.sleep(0.1)
        print("[gamepad] 입력 수신 OK")

    def get_action(self) -> dict[str, float]:
        s = self._live_state()
        action = {"delta_x": 0.0, "delta_y": 0.0, "delta_z": 0.0}
        if s is not None:

            def axis(v: float) -> float:
                return 0.0 if abs(v) < self.config.deadzone else float(np.clip(v, -1.0, 1.0))

            # XInput 스틱: 위 = +, 오른쪽 = +
            action["delta_x"] = self.config.x_sign * axis(s.get("ly", 0.0))  # 왼쪽 스틱 위 -> 앞(+x)
            action["delta_y"] = self.config.y_sign * -axis(s.get("lx", 0.0))  # 왼쪽 스틱 왼쪽 -> +y
            action["delta_z"] = self.config.z_sign * axis(s.get("ry", 0.0))  # 오른쪽 스틱 위 -> 위(+z)
        if self.config.use_gripper:
            gripper = GRIPPER_STAY
            if s is not None:
                close, open_ = s.get("rt", 0.0) > 0.5, s.get("lt", 0.0) > 0.5
                if self.config.swap_gripper:
                    close, open_ = open_, close
                if close and not open_:
                    gripper = GRIPPER_CLOSE
                elif open_ and not close:
                    gripper = GRIPPER_OPEN
            action["gripper"] = float(gripper)
        return action

    def get_teleop_events(self) -> dict[TeleopEvents, bool]:
        s = self._live_state()
        rb = s is not None and bool(int(s.get("btn", 0)) & BUTTONS["rb"])
        success = self.pop_pressed("y")
        failure = self.pop_pressed("a")
        rerecord = self.pop_pressed("x")
        return {
            # 연결이 끊기면 always_intervene여도 개입 안 함 -> 액션 0 (정지)
            TeleopEvents.IS_INTERVENTION: s is not None and (self.config.always_intervene or rb),
            TeleopEvents.TERMINATE_EPISODE: failure or rerecord,
            TeleopEvents.SUCCESS: success,
            TeleopEvents.RERECORD_EPISODE: rerecord,
        }

    def disconnect(self) -> None:
        self._running = False
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None

    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    def send_feedback(self, feedback: dict) -> None:
        pass
