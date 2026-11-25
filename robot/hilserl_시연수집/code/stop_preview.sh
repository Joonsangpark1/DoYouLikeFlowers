#!/bin/bash
# 카메라 미리보기(view_cams.py / view_c270.py) 끄기 (11-23, 녹화 전에)
for p in $(ps -eo pid,args | grep -E "view_cams.py|view_c270.py" | grep python | grep -v grep | awk '{print $1}'); do kill $p; done
sleep 1
ps -eo args | grep -E "view_cams.py|view_c270.py" | grep python | grep -v grep || echo "미리보기 꺼짐"
