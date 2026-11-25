#!/bin/bash
# 실행 중인 로봇 프로그램 확인 (11-23): run_remote_policy / record_prior / teleop 프로세스, 걸린 곳, 포트
ps -eo pid,etime,stat,args | grep -E 'run_remote_policy|record_prior|teleop_wrist' | grep python | grep -v grep
for p in $(ps -eo pid,args | grep -E 'run_remote_policy|record_prior|teleop_wrist' | grep python | grep -v grep | awk '{print $1}'); do
  echo "PID $p wchan=$(cat /proc/$p/wchan 2>/dev/null)"
  ls -l /proc/$p/fd 2>/dev/null | grep -E 'tty' | head -3
done
ss -tnp 2>/dev/null | grep -E ':5557|:5558|:5559|:8080' | head
true
