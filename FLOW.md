# 전체 흐름 — frontend → observe → actuate(HIL-SERL) → DATAS

각 폴더의 `PLAN.md`는 모듈별 상세 계획이고, 이 문서는 네 모듈이 실제로 어떻게 이어지는지
하나의 실행 시퀀스로 정리한 것이다.

## 한 번의 "꽃다발 완성" 실행 시퀀스

```
[1] frontend
    사용자가 3D 시뮬레이터에서 꽃다발 조립 + 추천 참고 → 확정
    → DATAS/recipes/{recipe_id}.json 저장
       {species, color, count, target_slot(xyz+angle)} 리스트

[2] 오케스트레이터 (신규, 작은 실행 스크립트 — 아래 "오케스트레이터" 절 참고)
    레시피를 한 줄씩(item) 순회 시작

    for item in recipe.items:
      [3] observe 호출
          wide-view 카메라로 트레이 탐지 → species/color 매칭되는 후보 선정
          → {instance_id, approx_world_xy} 반환

      [4] 오케스트레이터: 스크립트 기반 접근
          approx_world_xy 위로 IK 기반 pre-grasp 자세까지 이동 (자유공간 이동, 학습 불필요)

      [5] actuate: flower_pick (HIL-SERL 정책)
          접근 지점부터 인수인계 받아 정밀 grasp 수행
          reward classifier(or 사람) 가 성공/실패 판정

      [6] 오케스트레이터: 스크립트 기반 이동
          레시피의 target_slot 근처까지 이동 (자유공간)

      [7] actuate: flower_place (HIL-SERL 정책)
          기존 꽃과 충돌 회피하며 target_slot에 정밀 삽입
          reward classifier가 성공/실패 판정

      [8] (선택) observe 재확인
          꽃병 주변 재스캔 → 요구한 species/color가 실제 존재하는지 검증

      [9] DATAS/sessions/{recipe_id}.json에 item 처리 결과 로그
          (성공/실패, 재시도 횟수, 실패 시 어느 단계였는지)

    반복 종료 후 레시피 전체 완료 여부를 사용자에게 표시 (frontend로 상태 되돌림, 선택)
```

## 모듈 간 데이터 계약 (Contract)

| 전달 방향 | 내용 | 스키마 위치 |
|---|---|---|
| frontend → DATAS | 확정 레시피 | `DATAS/PLAN.md` recipes 스키마 |
| DATAS → observe/actuate | flower_catalog (species 정의 단일 소스) | `DATAS/PLAN.md` flower_catalog.json |
| observe → 오케스트레이터 | 후보 탐지 결과(대략 좌표) | `observe/PLAN.md` 출력 인터페이스 |
| 오케스트레이터/recipe → actuate | pick 접근 지점, place 목표(target_slot) | `actuate/PLAN.md` observe 인터페이스 절 |
| actuate/observe → DATAS | 학습 데이터, 세션 로그 | `DATAS/PLAN.md` 디렉토리 구조 |

## 오케스트레이터란?
지금 4개 폴더 어디에도 속하지 않는, "레시피를 읽고 observe/actuate를 순서대로 호출하는" 얇은 실행 로직이
필요하다. 아직 위치를 정하지 않았다 — 별도 `orchestrator/` 폴더를 새로 만들지, 아니면 `actuate` 안에
포함시킬지는 열린 질문이다. 역할 자체는 복잡하지 않다(순회 + 함수 호출 + 로깅 수준).

## 좌표계 통일이 선행 조건
observe의 `approx_world_xy`, actuate의 EE bound, frontend의 `target_slot`이 전부 같은 좌표계(로봇 베이스
기준)를 공유해야 흐름이 성립한다. 즉 **카메라-로봇 캘리브레이션**과 **꽃병 위치를 로봇 좌표계에 고정**하는 작업이
파이프라인 전체의 선행 조건이다. (`observe/PLAN.md`, `actuate/PLAN.md` 양쪽의 "미정" 항목에 이미 표시됨)

## 아직 확정 안 된 핵심 설계 질문 (사용자 판단 필요)
1. **스크립트 접근 ↔ HIL-SERL 인수인계 경계 반경**: observe 좌표 오차가 실측으로 얼마나 나오는지 봐야 정할 수 있음
2. **오케스트레이터 위치**: 별도 폴더 vs actuate 내부
3. **인스턴스 재선정 로직**: 같은 프레임에서 여러 개 요구되는 species(예: 장미 3개)를 어떻게 순서대로 소진할지
   (observe가 매번 재탐지하면서 이미 집은 위치를 피하는 방식이 제일 단순 — 확정 전 제안 단계)
