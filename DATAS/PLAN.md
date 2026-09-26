# DATAS — 데이터 저장/관리

## 역할
`frontend`, `observe`, `actuate` 세 모듈이 공유하는 데이터의 단일 소스(single source of truth).
각 모듈이 독립적으로 데이터를 만들되, 스키마와 클래스 정의(꽃 종류명 등)는 여기서 통일한다.

## 디렉토리 구조 (초안)
```
DATAS/
  flower_catalog.json        # 꽃 종류 마스터 데이터 (frontend·observe 공통 참조)
  recipes/                   # frontend에서 확정된 꽃다발 레시피
    {recipe_id}.json
  vision_dataset/            # observe 학습용 실측 촬영 데이터 (YOLO species 탐지)
    images/
    labels/                  # CVAT/Roboflow 등에서 export한 라벨
    class_map.json           # flower_catalog의 species와 라벨 클래스 매핑
  lerobot_episodes/          # actuate HIL-SERL 데모/RL 상호작용 데이터 (LeRobotDataset 포맷)
    flower_pick/
    flower_place/
  reward_classifiers/        # actuate HIL-SERL reward classifier 체크포인트 (스킬별)
    flower_pick/
    flower_place/
  sessions/                  # 실행 로그: 레시피 처리 결과, observe 배치 후 검증 결과 등 (추천 v2 재료 겸함)
```

## flower_catalog.json — 모든 모듈의 공통 기준점
```json
{
  "species": "rose",
  "display_name_ko": "장미",
  "colors": ["red", "white", "pink"],
  "season": ["spring", "autumn"],
  "price_tier": "mid",
  "meaning": "사랑, 열정",
  "avg_stem_length_cm": 40
}
```
- frontend: 카탈로그 팔레트 + 추천 로직의 입력
- observe: 라벨 클래스 정의의 기준 (`class_map.json`이 이 species 이름을 그대로 참조)
- 신규 꽃 종류 추가 시 **여기부터 업데이트 → observe 재촬영/재라벨링 트리거**되는 흐름을 표준 프로세스로 삼는다

## 버전 관리 방침
- `flower_catalog.json`, 레시피 스키마 등 구조화 데이터는 git으로 버전관리
- `vision_dataset/images`, `lerobot_episodes`(영상 포함)는 용량이 커질 가능성이 높음 → git 대신
  별도 스토리지(로컬 대용량 드라이브 또는 필요 시 HuggingFace Hub — LeRobot 데이터셋은 HF Hub 업로드가 표준 워크플로우)
  → 아직 최종 결정 아님, 데이터 양이 늘어나는 시점에 재검토

## 개발 단계
1. `flower_catalog.json` 초안 작성 (다루기로 한 꽃 3~5종부터)
2. `recipes/` 스키마를 frontend와 맞춰 확정
3. `vision_dataset/` 구조 확정 후 observe 촬영 시작
4. `lerobot_episodes/`는 LeRobot 표준 데이터셋 포맷을 그대로 사용 (actuate 문서 참고)

## 미정 / 다음 논의 필요
- 대용량 데이터(이미지, 영상) 저장소를 로컬로 계속 둘지, HF Hub 등 외부로 올릴지
- 세션/추천 로그를 언제부터 수집 시작할지 (추천 v1은 이 데이터 없이도 동작하므로 필수는 아님)
