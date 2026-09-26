import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import Vase from './components/Vase'
import SlotMarker from './components/SlotMarker'
import Palette from './components/Palette'
import ConfirmBar from './components/ConfirmBar'
import { useBouquetStore } from './store/useBouquetStore'
import './App.css'

export default function App() {
  const template = useBouquetStore((s) => s.template)
  const slots = useBouquetStore((s) => s.slots)

  return (
    <div className="app">
      <Palette />
      <div className="scene-wrap">
        <Canvas camera={{ position: [0.25, 0.2, 0.25], fov: 40 }}>
          <ambientLight intensity={0.7} />
          <directionalLight position={[0.3, 0.5, 0.2]} intensity={0.8} />
          <Vase vase={template.vase} />
          {Object.values(slots).map((slot) => (
            <SlotMarker key={slot.slot_id} slot={slot} />
          ))}
          <gridHelper args={[0.4, 20]} />
          <OrbitControls target={[0, 0.1, 0]} />
        </Canvas>
      </div>
      <ConfirmBar />
    </div>
  )
}
