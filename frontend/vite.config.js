import { randomUUID } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 개발 단계 전용: frontend가 나중에 웹으로 공개되면 이 미들웨어는 실제 API 서버로
// 교체된다. src/lib/saveRecipe.js 쪽 호출부만 바뀌고 나머지 앱 코드는 그대로 유지되도록
// "레시피 저장" 책임을 이 경계 하나에 몰아둔 것.
function localRecipeSavePlugin() {
  const recipesDir = path.resolve(import.meta.dirname, '../DATAS/recipes')

  return {
    name: 'local-recipe-save',
    configureServer(server) {
      server.middlewares.use('/api/save-recipe', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405
          res.end('Method Not Allowed')
          return
        }
        let body = ''
        req.on('data', (chunk) => {
          body += chunk
        })
        req.on('end', () => {
          try {
            const recipe = JSON.parse(body)
            recipe.recipe_id ??= randomUUID()
            recipe.created_at = new Date().toISOString()

            fs.mkdirSync(recipesDir, { recursive: true })
            const filePath = path.join(recipesDir, `${recipe.recipe_id}.json`)
            fs.writeFileSync(filePath, JSON.stringify(recipe, null, 2), 'utf-8')

            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ ok: true, recipe_id: recipe.recipe_id, path: filePath }))
          } catch (err) {
            res.statusCode = 500
            res.end(JSON.stringify({ ok: false, error: String(err) }))
          }
        })
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), localRecipeSavePlugin()],
  server: {
    fs: {
      // DATAS/(flower_catalog.json, vase_templates/*)를 형제 폴더에서 바로 import하기 위해 허용
      allow: ['..'],
    },
  },
})
