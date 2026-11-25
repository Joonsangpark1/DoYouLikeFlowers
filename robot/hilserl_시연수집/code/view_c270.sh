#!/bin/bash
# WSL에서 C270 미리보기 실행 (localhost:8081)
cd "$(dirname "$0")" && exec ~/miniforge3/envs/lerobot/bin/python -u view_c270.py
