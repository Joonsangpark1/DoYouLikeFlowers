import { DoubleSide } from 'three'

export default function Vase({ vase }) {
  const { radius_bottom_m, radius_top_m, height_m } = vase
  return (
    <mesh position={[0, height_m / 2, 0]}>
      <cylinderGeometry args={[radius_top_m, radius_bottom_m, height_m, 32, 1, true]} />
      <meshStandardMaterial
        color="#bcd4e0"
        transparent
        opacity={0.35}
        side={DoubleSide}
        metalness={0.1}
        roughness={0.15}
      />
    </mesh>
  )
}
