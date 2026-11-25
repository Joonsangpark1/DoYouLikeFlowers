#!/bin/bash
cd "$(dirname "$0")" || exit 1
~/miniforge3/envs/lerobot/bin/python -m py_compile "$1" && echo compiled
timeout 90 ~/miniforge3/envs/lerobot/bin/python -c "import ${1%.py}; print(\"import ok\")" 2>&1 | grep -vE "realsense" | tail -2
