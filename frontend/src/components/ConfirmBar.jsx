import { useState } from 'react'
import { useBouquetStore } from '../store/useBouquetStore'
import { saveRecipe } from '../lib/saveRecipe'

export default function ConfirmBar() {
  const slots = useBouquetStore((s) => s.slots)
  const template = useBouquetStore((s) => s.template)
  const reset = useBouquetStore((s) => s.reset)
  const [status, setStatus] = useState(null)

  const filled = Object.values(slots).filter((s) => s.species)
  const total = Object.values(slots).length

  const handleConfirm = async () => {
    setStatus('저장 중...')
    const recipe = {
      vase_template: template.template_id,
      slots: filled.map((s) => ({
        slot_id: s.slot_id,
        tier: s.tier,
        species: s.species,
        color: s.color,
        target_slot: s.target_slot,
      })),
    }
    try {
      const result = await saveRecipe(recipe)
      setStatus(`저장 완료 (recipe_id: ${result.recipe_id})`)
    } catch (err) {
      setStatus(`저장 실패: ${err.message}`)
    }
  }

  return (
    <div className="confirm-bar">
      <span>
        {filled.length} / {total} 슬롯 채움
      </span>
      <button onClick={handleConfirm} disabled={filled.length === 0}>
        확정
      </button>
      <button onClick={reset} className="secondary">
        초기화
      </button>
      {status && <span className="status">{status}</span>}
    </div>
  )
}
