import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

/**
 * SciFiLabBackground — High-tech command center laboratory background
 * matching the Iron Man reference image:
 * - Holographic control panels and floating monitors with blue glow
 * - Futuristic sci-fi room architecture (arches, glowing floors)
 * - Distant planet and futuristic city skyline visible through giant windows
 */
export function SpaceBackground() {
  const monitorsGroupRef = useRef()
  const ringRef = useRef()
  const particlesRef = useRef()

  const particlePositions = useMemo(() => {
    const pos = new Float32Array(800 * 3)
    for (let i = 0; i < 800; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 40
      pos[i * 3 + 1] = (Math.random() - 0.5) * 25
      pos[i * 3 + 2] = (Math.random() - 0.5) * 40 - 10
    }
    return pos
  }, [])

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    if (monitorsGroupRef.current) {
      monitorsGroupRef.current.rotation.y = Math.sin(t * 0.1) * 0.05
    }
    if (ringRef.current) {
      ringRef.current.rotation.z = t * 0.2
    }
    if (particlesRef.current) {
      particlesRef.current.rotation.y = t * 0.03
    }
  })

  return (
    <group>
      {/* ==================== SCI-FI LABORATORY ENVIRONMENT ==================== */}
      {/* Giant circular window frame (Command Center Portal) */}
      <mesh position={[0, 0, -18]}>
        <ringGeometry args={[12, 14, 64]} />
        <meshStandardMaterial
          color="#00aaff"
          emissive="#00aaff"
          emissiveIntensity={1.5}
          side={THREE.DoubleSide}
        />
      </mesh>
      <mesh position={[0, 0, -18.2]}>
        <circleGeometry args={[12, 64]} />
        <meshBasicMaterial color="#020510" />
      </mesh>

      {/* Distant Planet / Earth view through window */}
      <mesh position={[2, 3, -25]}>
        <sphereGeometry args={[6, 32, 32]} />
        <meshStandardMaterial
          color="#1a3b6c"
          emissive="#0a1b3c"
          emissiveIntensity={0.5}
          roughness={0.7}
        />
      </mesh>
      <mesh position={[2, 3, -24.8]} rotation={[0.5, 0.2, 0]}>
        <ringGeometry args={[6.5, 8.5, 64]} />
        <meshBasicMaterial color="#00aaff" transparent opacity={0.15} side={THREE.DoubleSide} />
      </mesh>

      {/* Futuristic City Skyline in background */}
      <group position={[0, -4, -22]}>
        {Array.from({ length: 15 }).map((_, i) => {
          const w = 1 + Math.random() * 1.5
          const h = 4 + Math.random() * 8
          const x = (i - 7) * 2.2
          return (
            <mesh key={i} position={[x, h / 2, 0]}>
              <boxGeometry args={[w, h, 1]} />
              <meshStandardMaterial
                color="#050814"
                emissive="#00aaff"
                emissiveIntensity={0.1 + Math.random() * 0.2}
              />
            </mesh>
          )
        })}
      </group>

      {/* ==================== HOLOGRAPHIC MONITORS & LAB SCREENS ==================== */}
      <group ref={monitorsGroupRef} position={[0, 0, 0]}>
        {/* Left Hologram Screen */}
        <mesh position={[-5, 1, -6]} rotation={[0, 0.4, 0]}>
          <planeGeometry args={[4, 2.5]} />
          <meshBasicMaterial color="#00aaff" transparent opacity={0.12} side={THREE.DoubleSide} />
        </mesh>
        {/* Right Hologram Screen */}
        <mesh position={[5, 1, -6]} rotation={[0, -0.4, 0]}>
          <planeGeometry args={[4, 2.5]} />
          <meshBasicMaterial color="#00aaff" transparent opacity={0.12} side={THREE.DoubleSide} />
        </mesh>

        {/* Floating holographic globe in center-right */}
        <mesh position={[3, -1, -4]}>
          <sphereGeometry args={[0.8, 24, 24]} />
          <meshBasicMaterial color="#00ffff" wireframe transparent opacity={0.3} />
        </mesh>
      </group>

      {/* ==================== FLOATING ENERGY PARTICLES ==================== */}
      <points ref={particlesRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={particlePositions.length / 3}
            array={particlePositions}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          size={0.08}
          color="#00aaff"
          transparent
          opacity={0.6}
          sizeAttenuation
          blending={THREE.AdditiveBlending}
        />
      </points>

      {/* Ambient lighting in lab */}
      <directionalLight position={[0, 10, 5]} intensity={1.5} color="#00aaff" />
      <pointLight position={[0, -2, 2]} intensity={2.0} color="#00ffff" distance={10} />
    </group>
  )
}
