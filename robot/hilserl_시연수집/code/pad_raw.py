"""게임패드 송신기 원본 JSON을 N초 받아서 보여줌 (11-22 점검). 사용: python pad_raw.py [초]"""
import json, socket, sys, time

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 5
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", 5557)); srv.listen(1); srv.settimeout(15)
conn, _ = srv.accept(); conn.settimeout(1)
buf, t0, seen, n = b"", time.time(), {}, 0
while time.time() - t0 < secs:
    try:
        buf += conn.recv(4096)
    except socket.timeout:
        continue
    *lines, buf = buf.split(b"\n")
    for l in lines:
        try:
            m = json.loads(l)
        except Exception:
            continue
        n += 1
        for k, v in m.items():
            if isinstance(v, (int, float)) and k != "btn":
                lo, hi = seen.get(k, (v, v)); seen[k] = (min(lo, v), max(hi, v))
        if m.get("btn"):
            seen.setdefault("btn_bits", set()).add(m["btn"])
print(f"{n}개 메시지 / {secs:.0f}초")
for k, v in seen.items():
    print(" ", k, v)
