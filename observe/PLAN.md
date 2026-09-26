# observe — 꽃 인지(perception) 모듈

## 역할
SO-101에 부착/거치된 카메라로 실제 작업 공간(꽃 트레이/꽃병 주변)을 보고,
`frontend`에서 확정된 레시피(`DATAS/recipes/*.json`)가 요구하는 꽃(species, color)이
현재 장면 어디에(픽셀 좌표 → 대략적 로봇/월드 좌표) 있는지 찾아 `actuate`에 넘긴다.

## observe와 actuate(HIL-SERL) 역할 분리 — 중요
`actuate`가 HIL-SERL로 결정되면서, HIL-SERL 자체에도 카메라 기반 **reward classifier**(성공/실패 판정용
경량 비전 모델)가 내장된다. 이건 observe와 목적이 다르다:

| | observe | HIL-SERL reward classifier (actuate 내부) |
|---|---|---|
| 시점 | 매 pick 이전, 장면 전체를 훑는 "무엇을 어디서 집을지" 결정 | pick/place 동작 도중, "지금 성공했는지" 순간 판정 |
| 출력 | 꽃 종류/색상 분류 + 대략적 좌표 (task-level) | 이진 성공/실패 (control-loop level) |
| 학습 대상 | 다종 꽃 species/color 분류기 | pick 1개, place 1개짜리 전용 이진 분류기 |

즉 **observe는 "장면 이해 + 타겟 선정"에 집중하고, 정밀한 성공 판정은 actuate 쪽 reward classifier에 맡긴다.**
이 경계를 넘어서 observe가 grasp 성패까지 판단하려 하지 않는 것을 권장.

## 추천하는 observe의 구체적 역할 (제안)

### 1. 장면 전체 인스턴스 탐지 + 분류 (wide-view)
- 고정 카메라로 꽃 트레이 전체를 촬영, 개별 꽃 인스턴스 탐지
- 경량 detector 추천: **YOLOv8n/YOLO11n** — SO-101과 함께 쓰는 저사양 PC/엣지에서도 실시간 추론 가능한 크기
  (HIL-SERL의 reward classifier가 ResNet10 CNN을 쓰는 것과 별개 모델 — 목적이 다르므로 공유하지 않는 것을 권장)
- species 분류는 detector의 클래스 헤드로 함께 처리(다중 클래스 detection)

### 2. 색상 분류는 별도 학습 없이 규칙 기반으로 시작
- detection bbox를 크롭한 뒤 HSV 히스토그램 기반 색상 판별
- 장점: 색상 라벨링 데이터를 따로 안 모아도 됨, species보다 색상 변형(빨강 장미의 톤 차이 등)이 더 다양해서
  규칙 기반이 초기엔 오히려 안정적일 수 있음
- 색상 구분이 애매한 species가 늘어나면 그때 CNN 분류기로 전환 검토 (지금은 과설계 방지)

### 3. 레시피 매칭 + 대략적 좌표 산출
- frontend 레시피의 `{species, color, count}` 요구를 탐지 결과와 매칭해 "다음에 집을 후보 1개" 선정
- 3D 위치는 깊이 카메라 없이: 카메라-로봇 캘리브레이션 + "트레이는 평평하다" 가정으로 픽셀→월드 xy 변환
  (정밀도는 필요 없음 — actuate의 HIL-SERL `flower_pick`이 근접 오차를 학습으로 흡수하는 구조이므로 observe는
  "대략 여기"만 주면 됨. 이게 observe 쪽 정밀 3D 추정 부담을 크게 낮춰준다)
- 이미 집은 개체를 다시 고르지 않도록 세션 내에서 탐지 인스턴스에 임시 ID 부여(위치 기반 매칭으로 충분, 꽃은
  스스로 움직이지 않으므로 복잡한 tracking 알고리즘 불필요)

### 4. (권장, 추가 제안) 배치 후 검증 패스
- actuate가 `flower_place`를 마친 뒤, observe가 꽃병 주변을 다시 한 번 훑어서
  "요구한 species/color가 target_slot 근처에 실제로 존재하는지" 확인
- 실패 시 로그를 `DATAS/sessions/`에 남겨 추후 원인 분석(어느 스킬 단계에서 실패가 몰리는지) 및
  reward classifier 재학습 데이터로 활용 가능 — 지금 단계는 제안일 뿐, 구현 우선순위는 낮음

## 데이터 확보 전략: 직접 촬영 + 라벨링 (기존 결정 유지)
- 대상: `DATAS/flower_catalog.json` 기준 종 리스트
- YOLO 학습용 라벨: bbox + species 클래스 (color는 라벨링 불필요, 규칙 기반이므로)
- 라벨링 툴: CVAT 또는 Roboflow (여전히 미정, 팀 규모/보안 요구로 결정)
- 최소 목표치(초안): 종당 200~300장, 겹침/가림 케이스 별도 확보

## 출력 인터페이스 (갱신)
```json
{
  "frame_id": "...",
  "detections": [
    {
      "instance_id": "tmp-3",
      "species": "rose",
      "color": "red",
      "bbox": [x1, y1, x2, y2],
      "conf": 0.92,
      "approx_world_xy": [x, y]
    }
  ]
}
```
- `world_z`(높이)는 트레이 평면 고정값으로 별도 관리(캘리브레이션 결과), 매 프레임 추정하지 않음
- actuate 오케스트레이터가 레시피 요구량과 `approx_world_xy`를 받아 스크립트 접근 → HIL-SERL 인수인계

## 개발 단계
1. 카메라-로봇 캘리브레이션 + "트레이 평면" 가정 검증 (actuate와 공동, `flower_pick` bound 설계 전 선행)
2. 촬영 프로토콜 확정 (카메라 위치/조명/배경 표준화)
3. 꽃 3~5종 파일럿 데이터셋 수집 + 라벨링 → YOLO 베이스라인 학습
4. HSV 색상 분류 규칙 작성 + 정확도 확인
5. 레시피 매칭 + 인스턴스 임시 ID 로직 구현 → actuate 오케스트레이터와 연동 테스트
6. (선택) 배치 후 검증 패스 추가

## 미정 / 다음 논의 필요
- 카메라-로봇 좌표 캘리브레이션 구체적 방법(체커보드 등)
- 라벨링 툴 선정
- "대략적 좌표"의 허용 오차 범위 — actuate의 `flower_pick` EE bound 크기와 맞물려 결정해야 함
