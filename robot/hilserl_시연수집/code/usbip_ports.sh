#!/bin/bash
# WSL 안 usbip 가상 포트 보기/떼기 (11-23, 프로그램이 usb_kill_urb에서 멈췄을 때). root로 실행.
# 사용: wsl -u root -- bash usbip_ports.sh [detach]
P=/var/run/usbipd-win/usbip
[ -x "$P" ] || P=$(command -v usbip)
echo "usbip = $P"
"$P" port 2>&1
if [ "$1" = "detach" ]; then
  for n in $("$P" port 2>/dev/null | sed -n 's/^Port \([0-9]*\):.*/\1/p'); do
    echo "detach port $n"; "$P" detach -p "$n"
  done
fi
true
