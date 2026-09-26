// 지금은 로컬 dev 서버 미들웨어(../../vite.config.js)가 DATAS/recipes/에 파일로 저장한다.
// frontend가 웹으로 공개되면 이 함수 내부만 실제 API 엔드포인트 호출로 바꾸면 되고,
// 호출부(ConfirmBar 등)는 그대로 둔다 — "레시피 저장" 책임을 이 경계 하나로 고정.
export async function saveRecipe(recipe) {
  const res = await fetch('/api/save-recipe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(recipe),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}
