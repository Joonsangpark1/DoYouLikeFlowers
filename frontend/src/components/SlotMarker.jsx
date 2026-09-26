import { useBouquetStore } from '../store/useBouquetStore'
import { toThreeVec3 } from '../lib/coords'
import FlowerModel from './FlowerModel'

export default function SlotMarker({ slot }) {
  const assignSlot = useBouquetStore((s) => s.assignSlot)

  const handleClick = (e) => {
    e.stopPropagation()
    assignSlot(slot.slot_id)
  }

  if (slot.species) {
    return (
      <group onClick={handleClick}>
        <FlowerModel species={slot.species} color={slot.color} targetSlot={slot.target_slot} />
      </group>
    )
  }

  const [tx, ty, tz] = toThreeVec3(slot.target_slot.xyz)
  return (
    <mesh position={[tx, ty, tz]} onClick={handleClick}>
      <sphereGeometry args={[0.006, 12, 12]} />
      <meshStandardMaterial
        color={slot.tier === 'focal' ? '#8899aa' : '#c9d3da'}
        transparent
        opacity={0.6}
      />
    </mesh>
  )
}
