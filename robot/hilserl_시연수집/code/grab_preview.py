"""녹화 미리보기(8080/stream)에서 사진 1장 저장 (11-23, 녹화를 안 건드리고 화면 상태·전압 확인용)."""
import sys, urllib.request
url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080/stream"
out = sys.argv[2] if len(sys.argv) > 2 else "/mnt/d/data/flower/preview_now.jpg"
buf = b""
with urllib.request.urlopen(url, timeout=5) as r:
    while len(buf) < 3_000_000:
        buf += r.read(65536)
        s = buf.find(b"\xff\xd8")
        e = buf.find(b"\xff\xd9", s + 2)
        if s >= 0 and e > s:
            open(out, "wb").write(buf[s:e + 2])
            print("saved", out)
            break
