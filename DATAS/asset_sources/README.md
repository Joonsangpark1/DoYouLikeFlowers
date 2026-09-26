# asset_sources — 외부에서 받아온 원본 에셋 보관

여기는 CC 라이선스 등으로 확보한 원본 3D/이미지 에셋 파일을 그대로 보관하는 곳.
실제로 앱에서 쓰는 변환/정리된 파일은 각 모듈 폴더(예: `frontend/public/models/`)에 따로 둔다 —
이 폴더는 "출처/라이선스 증빙"용 원본 보관소.

## Flowers by Quaternius
- 출처: https://poly.pizza/m/NBUxHir6FJ
- 라이선스: CC0 (Public Domain) — 저작자 표시 없이 상업/비상업 프로젝트에 자유롭게 사용 가능
- 원본 파일: `Flowers by Quaternius - NBUxHir6FJ.zip` (FBX)
- 실제 사용처: `frontend/public/models/flowers_quaternius.glb` (같은 모델을 GLB로 받아 변환 없이 바로 사용,
  `frontend/src/components/FlowerModel.jsx`에서 로드)
- 메쉬 매핑: `Flower_1` → 장미, `Flower_2` → 카네이션 (원본 아틀라스 텍스처는 버리고 형태만 사용,
  색상은 우리 팔레트 색으로 직접 칠함 — 이유는 `frontend/PLAN.md` 참고)
- 안개꽃은 이 에셋을 안 쓰고 절차적 구체 클러스터로 표현 (실제 안개꽃 형태에 더 가까움)
