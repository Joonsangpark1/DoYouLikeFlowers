# robot/ — SO-101 꽃 로봇 실물 코드

진행 기록은 `../PROGRESS.md`가 기준입니다. 작업 원본 위치는 노트북 `Desktop\로보틱스\` 등이고, 이 폴더는 그 사본입니다 (2026-11-18).

| 폴더 | 어디서 실행 | 내용 |
|---|---|---|
| `smolvla_데이터수집/` | 노트북 Windows + WSL | SmolVLA 데이터 수집 (손 시연→재생 녹화, Windows 카메라 송신기, usbipd, 캘리브레이션, 시작 자세) |
| `hilserl_시연수집/` | 노트북 WSL | HIL-SERL 시연. `code/record_prior.py` = VLA 종료 자세에서 시작하는 prior 시연 (카메라 2대, 액션 [dx,dy,dz,droll,gripper]) |
| `laptop/` | 노트북 WSL | `run_remote_policy.py` (서버 SmolVLA로 실물 실행), `go_start_pose.py` |
| `server/` | 학습·추론 서버 (RTX 5080) | 학습(`start_train.sh`, `train_smolvla.sh`), 추론 서버(`start_server.sh`, `serve_policy.py`), 오프라인 검증(`eval_trial*.py`, 결과 `eval_results/`) |
| `그리퍼_꽃병_설계/` | — | 그리퍼 패드·꽃병 홀더 CAD 생성 코드와 STL |

## 데이터셋 (Hugging Face, 비공개)

- `parkjoonsang/flower_reach_trial4` — 234 에피소드, 10 fps, 꽃 3종(rose / blue / sunflower) × 꽃병 배치 3개, 섞어서 수집. 현재 주력
- `parkjoonsang/flower_reach_trial3` — 183 에피소드 (손목 회전 캘리브레이션 기준이 trial4와 180° 다름, 섞지 말 것)

## trial4 SmolVLA 오프라인 검증 (2026-11-18)

| 시작 상태 | 꽃 고르기 | 바꾼 지시문을 따름 |
|---|---|---|
| 에피소드 첫 프레임 | 85% | 78% |
| 녹화용 start_pose.json | 66% | 55% |
| 첫 프레임 평균 (`start_pose_vla_trial4.json`) | **92%** | **88%** |
