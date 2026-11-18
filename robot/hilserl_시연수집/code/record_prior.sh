#!/usr/bin/env bash
# HIL-SERL prior(시연) 녹화 단축 명령 (11-17~). 자세한 설명은 record_prior.py 맨 위.
#   bash record_prior.sh                    # 처음
#   bash record_prior.sh --resume           # 이어서
#   bash record_prior.sh --resume --layout "blue,rose,sunflower"
# 그 전에 Windows: attach_usb.ps1(smolvla 폴더) + C270 송신기 + gamepad_sender.ps1, sior: start_server.sh
cd "$(dirname "$0")" || exit 1
exec "$HOME/miniforge3/envs/lerobot/bin/python" -u record_prior.py "$@"
