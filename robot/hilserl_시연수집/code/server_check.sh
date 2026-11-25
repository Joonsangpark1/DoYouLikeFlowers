#!/bin/bash
# 노트북 WSL에서 서버(sior) 포트 확인 (11-24): 8080 VLA 추론 서버, 50051 강화학습 학습기
H=${1:-100.120.78.64}
for p in 8080 50051; do
  if timeout 3 bash -c "</dev/tcp/$H/$p" 2>/dev/null; then echo "$p OK"; else echo "$p 연결 안 됨"; fi
done
ps -eo etime,args | grep -E 'flower_acto[r]|record_prio[r]' | head -3
