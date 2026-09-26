import { create } from 'zustand'
import { flowerCatalog, vaseTemplate } from '../data'

const speciesByName = Object.fromEntries(
  flowerCatalog.species_list.map((f) => [f.species, f]),
)

const initialSlots = Object.fromEntries(
  vaseTemplate.slots.map((s) => [s.slot_id, { ...s, species: null, color: null }]),
)

// 마지막 글자 받침 유무로 은/는 조사를 고른다
function withTopicParticle(word) {
  const code = word.charCodeAt(word.length - 1) - 0xac00
  if (code < 0 || code > 11171) return `${word}는`
  const hasBatchim = code % 28 !== 0
  return `${word}${hasBatchim ? '은' : '는'}`
}

export const useBouquetStore = create((set, get) => ({
  template: vaseTemplate,
  slots: initialSlots,
  selectedSpecies: null,
  selectedColor: null,
  message: null,

  setSelection: (species, color) => set({ selectedSpecies: species, selectedColor: color, message: null }),

  assignSlot: (slotId) => {
    const { selectedSpecies, selectedColor, slots } = get()
    const slot = slots[slotId]
    if (!slot) return

    if (!selectedSpecies) {
      set({ slots: { ...slots, [slotId]: { ...slot, species: null, color: null } }, message: null })
      return
    }

    const def = speciesByName[selectedSpecies]
    if (def.role !== slot.tier) {
      set({
        message: `${withTopicParticle(def.display_name_ko)} ${slot.tier === 'focal' ? '메인' : '필러'} 슬롯 전용이 아니에요.`,
      })
      return
    }

    set({
      slots: {
        ...slots,
        [slotId]: { ...slot, species: selectedSpecies, color: selectedColor },
      },
      message: null,
    })
  },

  reset: () => set({ slots: initialSlots, selectedSpecies: null, selectedColor: null, message: null }),
}))
