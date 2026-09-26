// 레시피/슬롯 템플릿은 z-up 실세계 좌표(x,y,z=높이)를 쓴다 (observe/actuate 문서와 동일 컨벤션).
// three.js는 y-up이므로 렌더링 직전, 이 함수에서만 변환한다 — 스토어/저장 데이터는 항상 z-up 그대로 유지.
export function toThreeVec3([x, y, z]) {
  return [x, z, y]
}
