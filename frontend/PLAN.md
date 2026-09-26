# frontend — 꽃다발 시뮬레이션 & 추천 인터페이스

## 역할
사용자가 원하는 꽃다발을 웹에서 3D로 조립/미리보기하고, 추천을 받아 최종 구성을 "확정"하면
그 확정 결과를 `DATAS`에 **꽃다발 레시피(JSON)** 로 저장한다. 이 레시피가 `observe`(어떤 꽃을 찾을지)와
`actuate`(어디에 어떻게 배치할지)의 목표 스펙이 된다. 즉 frontend는 로봇 파이프라인의 "명세 입력기"다.

## 확정된 설계 결정 (2026-09-22)
- **MVP 범위**: 수동 배치 UI부터 완성. 추천 기능은 2단계로 미룬다.
- **배치 방식**: 3D 자유 배치가 아니라 **고정 슬롯 템플릿**. 꽃병 모양에 미리 정의된 슬롯(자리)에
  꽃 종류만 채우는 방식 — UI가 단순해지고, 슬롯 좌표가 곧 로봇에게 넘길 `target_slot`이 되어 애매함이 없다.
- **초기 꽃 종류**: 3종 — 장미(rose, focal), 카네이션(carnation, focal), 안개꽃(baby_breath, filler).
  `DATAS/flower_catalog.json` 참고.
- **레시피 전달**: 로컬 파일 저장(같은 PC 가정). 단, **frontend는 나중에 웹으로 공개될 예정**이라 이
  가정이 영구적이지 않음 — 저장 로직을 `saveRecipe()` 함수 하나로 분리해서, 나중엔 내부 구현만
  실제 API 호출로 바꾸면 되게 만들어 둠 (아래 "저장 방식" 절 참고).

## 기술 스택 (적용됨)
- Vite + React 19 + react-three-fiber + drei + Zustand
- `frontend/` 자체가 Vite 프로젝트 루트, `npm run dev`로 실행 (http://localhost:5173)
- 3D 꽃 에셋: **CC0(퍼블릭 도메인) 저폴리곤 메쉬 적용됨** — "Flowers" by Quaternius (poly.pizza,
  https://poly.pizza/m/NBUxHir6FJ). 원본은 `DATAS/asset_sources/`에 보관, 실사용 파일은
  `public/models/flowers_quaternius.glb`. 장미=`Flower_1` 노드, 카네이션=`Flower_2` 노드 형태만 가져오고
  원본 아틀라스 텍스처는 버린 뒤 우리 팔레트 색으로 직접 칠함(정확한 색상 매핑을 위해 — 자세한 이유는
  `DATAS/asset_sources/README.md`). 안개꽃은 이 메쉬 대신 절차적 구체 클러스터 유지(실제 형태에 더 가까움).
  실물 사진으로 리텍스처하는 건 `observe`용 실측 촬영이 이뤄진 뒤로 미룸.

## 슬롯 템플릿
`DATAS/vase_templates/default_12slot.json`에 정의. 외곽 링 8슬롯(focal, 장미/카네이션용) +
내곽 링 4슬롯(filler, 안개꽃용), 좌표는 z-up(x,y,z=높이) 미터 단위, 꽃병 바닥 중심이 원점.
이 컨벤션은 `observe`/`actuate` 문서와 동일 — three.js 렌더링에서만 `src/lib/coords.js`의
`toThreeVec3`로 y-up 변환하고, 스토어/저장 데이터는 항상 z-up 그대로 유지한다.

focal/filler 구분은 `flower_catalog.json`의 `role` 필드로 강제됨 — 예: 장미를 filler 슬롯에 넣으려 하면
UI가 거부하고 안내 메시지를 띄운다 (`src/store/useBouquetStore.js`의 `assignSlot`).

## 핵심 기능 (구현 상태)

### 1. 꽃다발 조립 뷰 — 구현됨
- `src/components/Palette.jsx`: 종류/색상 선택
- `src/components/SlotMarker.jsx` + `FlowerModel.jsx`: 슬롯 클릭 → 선택된 꽃 배치, 채워진 슬롯 재클릭 → 비움
- 카메라는 drei `OrbitControls`로 자유 회전/줌 가능

### 2. 추천 기능 — 미구현 (2단계)
- 입력: 목적(생일/졸업/프로포즈/조문 등), 예산, 선호 색상, 계절
- 1차: content-based 필터링 — `flower_catalog.json`의 속성(색, 꽃말, 가격, 제철 여부)으로 후보 꽃 종류 스코어링
- 2차(추후): 사용자 확정 이력이 쌓이면 협업 필터링으로 고도화
- 추천 결과는 "완성된 꽃다발 1개"가 아니라 "꽃 조합 후보 3~5개"를 제시하고 사용자가 미세조정 가능하게

### 3. 확정(Confirm) → 레시피 출력 — 구현됨
- `src/components/ConfirmBar.jsx`에서 확정 클릭 시 채워진 슬롯만 모아 레시피 JSON 생성
- 스키마 (슬롯 기반, count 없이 슬롯 1개 = 꽃 1개):
```json
{
  "recipe_id": "uuid",
  "created_at": "ISO8601",
  "vase_template": "default_12slot",
  "slots": [
    {
      "slot_id": "A0",
      "tier": "focal",
      "species": "rose",
      "color": "red",
      "target_slot": { "xyz": [0.055, 0.0, 0.09], "angle_deg": 25 }
    }
  ]
}
```
- 빈 슬롯은 출력에 포함하지 않음 — 다운스트림(observe/actuate)은 이 배열만 순회하면 됨

## 저장 방식 (지금 vs 나중)
- **지금**: `src/lib/saveRecipe.js`가 `POST /api/save-recipe` 호출 → `vite.config.js`의
  `localRecipeSavePlugin`(Vite dev 서버 미들웨어)이 `DATAS/recipes/{recipe_id}.json`으로 직접 파일 저장.
  별도 서버 프로세스 관리 없이 `npm run dev` 하나로 끝나서 "같은 PC 로컬 저장" 요구를 만족시킴.
- **나중(웹 공개 시)**: `saveRecipe.js` 내부만 실제 배포된 API 엔드포인트로 바꾸면 됨.
  `ConfirmBar.jsx` 등 호출부는 변경 불필요 — 저장 책임이 이 파일 하나에 고정되어 있음.

## observe/actuate와의 연결고리
전체 흐름은 `../FLOW.md` 참고 (observe가 탐색 → actuate가 HIL-SERL로 pick/place).
슬롯 템플릿의 `target_slot`이 그대로 actuate `flower_place`의 목표 좌표로 쓰인다.

## 개발 단계
1. ~~MVP: 3종 placeholder, 고정 슬롯 배치, 확정 → JSON 저장까지~~ — **완료**
2. ~~실제 3D 꽃 에셋 교체 (placeholder → CC0 glTF)~~ — **완료**
3. 추천 v1: content-based 추천 로직 + UI
4. observe/actuate와 레시피 스키마 검증 (실제 좌표계 캘리브레이션 이후)
5. 협업 필터링 추천 v2 (사용자 데이터 축적 후)
6. 웹 공개 시점에 `saveRecipe.js`를 실서버 API로 전환

## 미정 / 다음 논의 필요
- 실물 촬영 후 CC0 메쉬를 우리 실제 꽃 사진 텍스처로 교체할지 (지금은 팔레트 색상 오버라이드로 대체 중)
- 로봇이 실제로 도달 가능한 배치 범위(작업공간)를 슬롯 템플릿 좌표에 제약으로 반영할지 여부
- 웹 공개 시 필요한 것: 인증/세션, 실 배포 API 서버, 3D 에셋 라이선스 재검토(CC0라 문제 없지만 재확인)
