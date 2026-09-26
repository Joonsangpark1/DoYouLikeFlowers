import { flowerCatalog } from '../data'
import { useBouquetStore } from '../store/useBouquetStore'

export default function Palette() {
  const selectedSpecies = useBouquetStore((s) => s.selectedSpecies)
  const selectedColor = useBouquetStore((s) => s.selectedColor)
  const setSelection = useBouquetStore((s) => s.setSelection)
  const message = useBouquetStore((s) => s.message)

  return (
    <div className="palette">
      <h1>꽃다발 시뮬레이터</h1>
      <p className="hint">
        종류/색상을 고르고 오른쪽 꽃병의 빈 슬롯을 클릭해 채우세요.
        <br />
        이미 채워진 슬롯을 클릭하면 비웁니다.
      </p>

      {flowerCatalog.species_list.map((f) => (
        <div key={f.species} className="palette-species">
          <div className="palette-species-name">
            {f.display_name_ko}{' '}
            <span className="palette-species-tier">({f.role === 'focal' ? '메인' : '필러'})</span>
          </div>
          <div className="palette-colors">
            {f.colors.map((c) => {
              const active = selectedSpecies === f.species && selectedColor === c
              return (
                <button
                  key={c}
                  className={`swatch swatch-${c} ${active ? 'active' : ''}`}
                  onClick={() => setSelection(f.species, c)}
                  title={c}
                />
              )
            })}
          </div>
        </div>
      ))}

      <button className="clear-selection" onClick={() => setSelection(null, null)}>
        선택 해제 (클릭 시 슬롯 비우기 모드)
      </button>

      {message && <div className="palette-message">{message}</div>}
    </div>
  )
}
