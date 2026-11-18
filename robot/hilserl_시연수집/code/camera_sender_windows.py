"""[Windows] 카메라를 Windows에서 직접 읽어 JPEG로 WSL 녹화 프로그램에 보낸다 (net 카메라). 녹화하는 동안 켜 둘 것.

왜: 2026-11-17 실측 — 같은 카메라가 Windows에서는 29.7 fps인데 usbipd로 WSL에 넘기면 6~7 fps + 깨진 프레임
(WSL 재시작해도 그대로). 그래서 카메라는 WSL로 넘기지 않고 Windows가 쥐고, 사진만 보낸다.
WSL의 실제 IP로 접속한다 (localhost 중계는 WSL 재시작 뒤 접속을 받는 척만 하고 끊는 경우가 있었음, 11-17).
WSL 프로그램이 안 켜져 있으면 1초마다 다시 시도.

준비: Windows Python에 opencv-python (pip install opencv-python). 카메라는 WSL에 attach하지 말 것
  (attach_usb.ps1이 알아서 떼고 이 송신기를 켬)
사용 (PowerShell):
  python camera_sender_windows.py                       # 카메라 index 0
  python camera_sender_windows.py --index 1
  python camera_sender_windows.py --find innomaker      # 손목 카메라를 찾아서 (번호가 바뀌어도 OK) -> 5558
  python camera_sender_windows.py --find c270 --port 5559 --exposure -5   # HIL-SERL 고정 카메라 (11-17)
프로토콜: [4바이트 big-endian 길이][JPEG 바이트] 반복. 해상도 640x480, 품질 90으로 다시 인코딩.

--find: DirectShow 번호는 꽂힌 카메라에 따라 바뀌어서, 카메라마다 다른 성질로 고른다 (11-17 실측)
  노트북 내장 = 1920x1080 가능 / 인텔 가상 카메라 = 640x480 요청해도 1280x720으로 나옴
  C270 = 최대 1280x960 / Innomaker = 최대 1280x720 + 640x480 그대로 나옴
--exposure: C270은 자동 노출이면 실내에서 15 fps로 떨어짐 → -5로 고정하면 30 fps
"""

import argparse
import socket
import struct
import subprocess
import time

import cv2


def _probe(index: int, w: int, h: int):
    """(최대 해상도 (h, w), w x h 요청 시 실제 (h, w)). 못 열면 None."""
    shapes = []
    for rw, rh in [(1920, 1080), (w, h)]:
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, rw)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, rh)
        ok, f = cap.read()
        cap.release()
        if not ok:
            return None
        shapes.append(f.shape[:2])
    return shapes[0], shapes[1]


def find_camera(kind: str, w: int, h: int, max_index: int = 6) -> int:
    for index in range(max_index):
        p = _probe(index, w, h)
        if p is None:
            continue  # 없는 번호 또는 다른 프로그램(다른 송신기)이 쓰는 중
        max_hw, req_hw = p
        if kind == "c270" and max_hw == (960, 1280):
            return index
        if kind == "innomaker" and max_hw == (720, 1280) and req_hw == (h, w):
            return index
    raise RuntimeError(f"{kind} 카메라를 못 찾음 (꽂혀 있는지, WSL에 attach돼 있지 않은지, 다른 프로그램이 쓰는지 확인)")


def open_camera(index: int, w: int, h: int, fps: int, exposure: float | None = None):
    # 로봇 카메라(Innomaker, 최대 720p)가 WSL에 붙어 있으면 index가 밀려서 노트북 내장 카메라(1080p)가 잡힘 (11-17 실제 발생)
    probe = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    probe.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    probe.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    ok, f = probe.read()
    probe.release()
    if ok and f.shape[0] >= 1080:
        raise RuntimeError(f"index {index}는 1080p 카메라 = 노트북 내장 카메라로 보임. 로봇 카메라가 WSL에 붙어 있으면 "
                           "PowerShell에서 usbipd detach --busid <카메라 busid> 후 다시 실행 (또는 --index 바꾸기)")
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, fps)
    if exposure is not None:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # DSHOW: 0.25 = 수동
        cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
    if not cap.isOpened():
        raise RuntimeError(f"카메라 index {index}를 못 엶 (WSL에 attach돼 있으면 usbipd detach 먼저)")
    ok, f = cap.read()
    if not ok or f.shape[:2] != (h, w):
        raise RuntimeError(f"index {index}: {None if not ok else f.shape} — {w}x{h}가 아님. 다른 --index 시도")
    return cap


def wsl_ip() -> str:
    """WSL의 실제 IP (wsl hostname -I 첫 번째). 실패하면 127.0.0.1."""
    try:
        out = subprocess.run(["wsl.exe", "-e", "hostname", "-I"], capture_output=True, timeout=10).stdout
        ip = out.decode("utf-8", "ignore").replace(chr(0), "").split()[0]
        socket.inet_aton(ip)
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--host", default="auto", help="auto = WSL 실제 IP (wsl hostname -I), 안 되면 127.0.0.1")
    ap.add_argument("--port", type=int, default=5558)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--quality", type=int, default=90)
    ap.add_argument("--find", choices=["innomaker", "c270"], help="--index 대신 카메라 종류로 찾기")
    ap.add_argument("--exposure", type=float, help="수동 노출 (C270은 -5). 안 주면 자동 노출")
    args = ap.parse_args()

    auto = args.host == "auto"
    host = wsl_ip() if auto else args.host
    if args.find:
        args.index = find_camera(args.find, args.width, args.height)
        print(f"{args.find} = index {args.index}")
    cap = open_camera(args.index, args.width, args.height, args.fps, args.exposure)
    print(f"카메라 index {args.index} {args.width}x{args.height} 열림 -> {host}:{args.port} 로 보냄 (Ctrl+C 종료)")
    enc = [int(cv2.IMWRITE_JPEG_QUALITY), args.quality]
    try:
        while True:
            try:
                sock = socket.create_connection((host, args.port), timeout=2)
            except OSError:
                print(f"[대기] WSL 프로그램이 아직 안 켜졌거나 종료됨 ({host}) -> 1초 뒤 다시 연결", flush=True)
                time.sleep(1)
                if auto:
                    host = wsl_ip()   # WSL 재시작 등으로 IP가 바뀌었을 수 있음
                continue
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print(f"[연결됨] WSL 프로그램과 연결 ({host})", flush=True)
            n, t0 = 0, time.time()
            try:
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        print("[카메라 읽기 실패] 다시 엶", flush=True)
                        cap.release()
                        time.sleep(0.5)
                        cap = open_camera(args.index, args.width, args.height, args.fps, args.exposure)
                        continue
                    _, jpg = cv2.imencode(".jpg", frame, enc)
                    data = jpg.tobytes()
                    sock.sendall(struct.pack(">I", len(data)) + data)
                    n += 1
                    if time.time() - t0 >= 10:
                        print(f"  {n / (time.time() - t0):.1f} fps 보내는 중", flush=True)
                        n, t0 = 0, time.time()
            except OSError:
                print("[끊김] WSL 프로그램 종료 -> 다시 연결 대기", flush=True)
                time.sleep(1)   # 바로 재접속을 반복하면 반쯤 열린 연결이 수백 개 쌓임 (11-17)
            finally:
                sock.close()
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()


if __name__ == "__main__":
    main()
