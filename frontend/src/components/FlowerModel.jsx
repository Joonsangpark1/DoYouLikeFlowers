import { useMemo } from 'react'
import { useGLTF } from '@react-three/drei'
import { toThreeVec3 } from '../lib/coords'

// CC0 (퍼블릭 도메인) 저폴리곤 꽃 메쉬 — "Flowers" by Quaternius, poly.pizza에서 확보.
// 원본 머티리얼(아틀라스 텍스처)은 종/색상별 정확한 틴트가 안 돼서 버리고,
// 형태(geometry)만 가져와 종류별 색상은 우리 팔레트 색으로 직접 칠한다.
// 원본은 FBX 기준(Z가 꽃의 "위쪽" 축)이라 로컬에서 -90도(X축) 보정 회전을 건 뒤 배치한다.
const MODEL_URL = '/models/flowers_quaternius.glb'

const COLOR_HEX = {
  red: '#d1495b',
  white: '#f7f7f2',
  pink: '#eab0c9',
}

// 노드별 실측 바운딩(glTF accessor min/max) 기준으로 우리 씬 스케일(약 2cm 머리)에 맞춘 값
const MESH_BY_SPECIES = {
  rose: { node: 'Flower_1', scale: 4.2 },
  carnation: { node: 'Flower_2', scale: 4.2 },
}

const STEM_LEN = 0.05
const HEAD_CORRECTION_ROTATION = [-Math.PI / 2, 0, 0]

function FlowerHead({ species, hex }) {
  const { nodes } = useGLTF(MODEL_URL)
  const def = MESH_BY_SPECIES[species]
  const geometry = nodes[def.node]?.geometry

  if (!geometry) return null

  return (
    <mesh geometry={geometry} scale={def.scale} rotation={HEAD_CORRECTION_ROTATION}>
      <meshStandardMaterial color={hex} />
    </mesh>
  )
}

export default function FlowerModel({ species, color, targetSlot }) {
  const [tx, ty, tz] = toThreeVec3(targetSlot.xyz)
  const tiltRad = (targetSlot.angle_deg * Math.PI) / 180
  const hex = COLOR_HEX[color] ?? '#cccccc'

  const babyBreathOffsets = useMemo(
    () =>
      Array.from({ length: 5 }, () => [
        (Math.random() - 0.5) * 0.015,
        0.008 + Math.random() * 0.012,
        (Math.random() - 0.5) * 0.015,
      ]),
    [],
  )

  return (
    <group position={[tx, ty, tz]} rotation={[0, 0, tiltRad]}>
      <mesh position={[0, -STEM_LEN / 2, 0]}>
        <cylinderGeometry args={[0.0015, 0.0015, STEM_LEN, 6]} />
        <meshStandardMaterial color="#4c7a3f" />
      </mesh>

      {species === 'baby_breath' ? (
        <group>
          {babyBreathOffsets.map((pos, i) => (
            <mesh key={i} position={pos}>
              <sphereGeometry args={[0.006, 6, 6]} />
              <meshStandardMaterial color={hex} />
            </mesh>
          ))}
        </group>
      ) : (
        <FlowerHead species={species} hex={hex} />
      )}
    </group>
  )
}

useGLTF.preload(MODEL_URL)
