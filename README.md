# DoYouLikeFlowers — 꽃꽂이 로봇

사람이 화면에서 꽃다발을 고르면, SO-101 로봇 팔이 꽃을 찾아 집어서 꽂는 것을 목표로 하는 프로젝트입니다.
2026-11-30 전시 시연이 목표입니다.

## 바로 실행해 보려면

**실물 로봇 코드와 설치·실행 안내는 [`robot/README.md`](robot/README.md)부터 보세요.**
설치(WSL·usbipd·LeRobot 고정 버전과 수정 패치) → 연결 → SmolVLA 데이터 수집·학습·실물 실행 → HIL-SERL 시연 녹화 순서로 정리돼 있습니다.

## 폴더

| 폴더/파일 | 내용 |
|---|---|
| [`robot/`](robot/README.md) | **실물 로봇 코드** (SmolVLA 데이터 수집·학습·추론, HIL-SERL 시연 녹화, 그리퍼·꽃병 CAD) |
| [`PROGRESS.md`](PROGRESS.md) | 날짜별 진행 기록 (무엇을 왜 바꿨는지, 실험 수치) |
| [`FLOW.md`](FLOW.md) | 전체 흐름: frontend → observe → actuate → DATAS |
| `frontend/` | 꽃다발을 3D로 고르는 웹 화면 (React + Vite) |
| `DATAS/` | 꽃 목록, 꽃병 템플릿, 3D 에셋 |
| `observe/`, `actuate/`, `orchestrator/` | 모듈별 계획·코드 |
| `decisions/` | 설계 결정 기록 |

## 지금 상태 (2026-11-22)

- **SmolVLA (꽃 앞까지 가기)**: 540 에피소드로 학습, 학습 사진 기준 지시한 꽃으로 가는 비율 89%. 꽃이 서로 가리면 자주 틀림
- **HIL-SERL (집어서 옮기기)**: 고정 카메라·작업 영역·시연 녹화 도구 준비 완료, 시연 수집 시작 단계
