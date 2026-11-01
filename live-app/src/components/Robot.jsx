import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

/**
 * OS_V1 — Exact Iron Man Black & Blue Armor Model
 * - Sleek futuristic black helmet with glowing electric blue visor
 * - Detailed cybernetic black armor plating with glowing blue energy conduits
 * - Central circular Arc Reactor with "OSS" glowing core
 * - Articulated shoulder pauldrons and mechanical joints
 */
export default function Robot({ mood = 'idle' }) {
  const headRef = useRef()
  const chestCoreRef = useRef()
  const arcRingRef = useRef()
  const bodyRef = useRef()
  const leftArmRef = useRef()
  const rightArmRef = useRef()

  useFrame(({ mouse, clock }) => {
    const t = clock.getElapsedTime()
    const cx = mouse.x * 0.3
    const cy = mouse.y * 0.2

    // Smooth head tracking
    if (headRef.current) {
      headRef.current.rotation.y = THREE.MathUtils.lerp(headRef.current.rotation.y, cx * 0.4, 0.05)
      headRef.current.rotation.x = THREE.MathUtils.lerp(headRef.current.rotation.x, -cy * 0.3, 0.05)
    }

    // Breathing / power pulse
    if (bodyRef.current) {
      const pulse = 1 + Math.sin(t * 2) * 0.008
      bodyRef.current.scale.setScalar(pulse)
    }

    // Arc reactor ring rotation
    if (arcRingRef.current) {
      arcRingRef.current.rotation.z = t * 1.5
    }

    // Chest core glow intensity based on mood
    if (chestCoreRef.current) {
      const intensity = mood === 'thinking' ? 2.5 : mood === 'happy' ? 3.0 : 2.0
      chestCoreRef.current.material.emissiveIntensity = intensity + Math.sin(t * 4) * 0.5
    }
  })

  const glowColor = mood === 'thinking' ? '#0088ff' : mood === 'happy' ? '#00ffff' : '#00aaff'

  return (
    <group position={[0, -0.2, 0]}>
      {/* ==================== TORSO & ARMOR ==================== */}
      <group ref={bodyRef}>
        {/* Main chest armor plate */}
        <mesh position={[0, 0, 0]} castShadow>
          <boxGeometry args={[1.2, 1.4, 0.7]} />
          <meshStandardMaterial
            color="#08080c"
            metalness={0.95}
            roughness={0.15}
            emissive="#020205"
            emissiveIntensity={0.2}
          />
        </mesh>

        {/* Chest pectoral armor plates (Iron Man style) */}
        <mesh position={[-0.32, 0.3, 0.32]} rotation={[0, 0, -0.1]}>
          <boxGeometry args={[0.5, 0.35, 0.12]} />
          <meshStandardMaterial color="#12121a" metalness={0.9} roughness={0.2} />
        </mesh>
        <mesh position={[0.32, 0.3, 0.32]} rotation={[0, 0, 0.1]}>
          <boxGeometry args={[0.5, 0.35, 0.12]} />
          <meshStandardMaterial color="#12121a" metalness={0.9} roughness={0.2} />
        </mesh>

        {/* Abdomen armor segments */}
        <mesh position={[0, -0.35, 0.34]}>
          <boxGeometry args={[0.7, 0.5, 0.1]} />
          <meshStandardMaterial color="#0b0b12" metalness={0.92} roughness={0.18} />
        </mesh>

        {/* ==================== ARC REACTOR (OSS Core) ==================== */}
        <group position={[0, 0.1, 0.38]}>
          {/* Outer ring */}
          <mesh ref={arcRingRef}>
            <torusGeometry args={[0.26, 0.03, 16, 48]} />
            <meshStandardMaterial
              color={glowColor}
              emissive={glowColor}
              emissiveIntensity={2.5}
              toneMapped={false}
            />
          </mesh>

          {/* Inner core disc */}
          <mesh ref={chestCoreRef} position={[0, 0, 0.02]}>
            <cylinderGeometry args={[0.2, 0.2, 0.04, 32]} />
            <meshStandardMaterial
              color="#ffffff"
              emissive={glowColor}
              emissiveIntensity={3.0}
              toneMapped={false}
            />
          </mesh>

          {/* Center text / emblem representation (OSS ring) */}
          <mesh position={[0, 0, 0.04]}>
            <ringGeometry args={[0.08, 0.14, 32]} />
            <meshStandardMaterial
              color="#00ffff"
              emissive="#00ffff"
              emissiveIntensity={2.0}
              side={THREE.DoubleSide}
            />
          </mesh>
        </group>

        {/* Blue glowing energy lines on chest */}
        <mesh position={[-0.4, 0, 0.37]}>
          <boxGeometry args={[0.04, 0.6, 0.02]} />
          <meshStandardMaterial color="#00aaff" emissive="#00aaff" emissiveIntensity={2.0} />
        </mesh>
        <mesh position={[0.4, 0, 0.37]}>
          <boxGeometry args={[0.04, 0.6, 0.02]} />
          <meshStandardMaterial color="#00aaff" emissive="#00aaff" emissiveIntensity={2.0} />
        </mesh>
      </group>

      {/* ==================== SHOULDERS & ARMS ==================== */}
      {/* Left Shoulder Pauldron */}
      <group position={[-0.8, 0.5, 0]}>
        <mesh castShadow>
          <sphereGeometry args={[0.3, 16, 16]} />
          <meshStandardMaterial color="#12121a" metalness={0.92} roughness={0.15} />
        </mesh>
        {/* Blue accent */}
        <mesh position={[0, 0.1, 0.2]}>
          <boxGeometry args={[0.15, 0.03, 0.02]} />
          <meshStandardMaterial color="#00aaff" emissive="#00aaff" emissiveIntensity={2.0} />
        </mesh>
      </group>

      {/* Right Shoulder Pauldron */}
      <group position={[0.8, 0.5, 0]}>
        <mesh castShadow>
          <sphereGeometry args={[0.3, 16, 16]} />
          <meshStandardMaterial color="#12121a" metalness={0.92} roughness={0.15} />
        </mesh>
        <mesh position={[0, 0.1, 0.2]}>
          <boxGeometry args={[0.15, 0.03, 0.02]} />
          <meshStandardMaterial color="#00aaff" emissive="#00aaff" emissiveIntensity={2.0} />
        </mesh>
      </group>

      {/* Left arm */}
      <mesh position={[-0.8, 0.05, 0]} castShadow>
        <cylinderGeometry args={[0.14, 0.12, 0.8, 16]} />
        <meshStandardMaterial color="#0a0a10" metalness={0.9} roughness={0.2} />
      </mesh>
      {/* Left forearm */}
      <mesh position={[-0.8, -0.55, 0.05]} castShadow>
        <cylinderGeometry args={[0.12, 0.1, 0.7, 16]} />
        <meshStandardMaterial color="#12121a" metalness={0.9} roughness={0.2} />
      </mesh>
      {/* Left glove / hand with glowing knuckles */}
      <mesh position={[-0.8, -0.95, 0.08]} castShadow>
        <boxGeometry args={[0.18, 0.2, 0.2]} />
        <meshStandardMaterial color="#08080c" metalness={0.95} roughness={0.1} />
      </mesh>
      <mesh position={[-0.8, -1.02, 0.18]}>
        <sphereGeometry args={[0.03, 8, 8]} />
        <meshStandardMaterial color="#00aaff" emissive="#00aaff" emissiveIntensity={2.5} />
      </mesh>

      {/* Right arm */}
      <mesh position={[0.8, 0.05, 0]} castShadow>
        <cylinderGeometry args={[0.14, 0.12, 0.8, 16]} />
        <meshStandardMaterial color="#0a0a10" metalness={0.9} roughness={0.2} />
      </mesh>
      {/* Right forearm */}
      <mesh position={[0.8, -0.55, 0.05]} castShadow>
        <cylinderGeometry args={[0.12, 0.1, 0.7, 16]} />
        <meshStandardMaterial color="#12121a" metalness={0.9} roughness={0.2} />
      </mesh>
      {/* Right glove / hand */}
      <mesh position={[0.8, -0.95, 0.08]} castShadow>
        <boxGeometry args={[0.18, 0.2, 0.2]} />
        <meshStandardMaterial color="#08080c" metalness={0.95} roughness={0.1} />
      </mesh>
      <mesh position={[0.8, -1.02, 0.18]}>
        <sphereGeometry args={[0.03, 8, 8]} />
        <meshStandardMaterial color="#00aaff" emissive="#00aaff" emissiveIntensity={2.5} />
      </mesh>

      {/* ==================== NECK ==================== */}
      <mesh position={[0, 0.82, 0]}>
        <cylinderGeometry args={[0.18, 0.22, 0.25, 16]} />
        <meshStandardMaterial color="#08080c" metalness={0.95} roughness={0.1} />
      </mesh>

      {/* ==================== HELMET (Iron Man Black Armor) ==================== */}
      <group ref={headRef} position={[0, 1.3, 0]}>
        {/* Main helmet skull */}
        <mesh castShadow>
          <sphereGeometry args={[0.42, 32, 32]} />
          <meshStandardMaterial color="#08080c" metalness={0.96} roughness={0.08} />
        </mesh>

        {/* Face plate — angular Iron Man style */}
        <mesh position={[0, -0.02, 0.32]}>
          <boxGeometry args={[0.62, 0.55, 0.25]} />
          <meshStandardMaterial color="#0c0c14" metalness={0.92} roughness={0.12} />
        </mesh>

        {/* Forehead crest fins (sharp aerodynamic sweeps) */}
        <mesh position={[-0.15, 0.35, -0.1]} rotation={[0, 0, -0.2]}>
          <boxGeometry args={[0.05, 0.25, 0.3]} />
          <meshStandardMaterial color="#00aaff" emissive="#00aaff" emissiveIntensity={1.5} />
        </mesh>
        <mesh position={[0.15, 0.35, -0.1]} rotation={[0, 0, 0.2]}>
          <boxGeometry args={[0.05, 0.25, 0.3]} />
          <meshStandardMaterial color="#00aaff" emissive="#00aaff" emissiveIntensity={1.5} />
        </mesh>

        {/* ==================== VISOR EYES (Glowing Blue Slits) ==================== */}
        {/* Left eye glowing slit */}
        <mesh position={[-0.16, 0.05, 0.42]} rotation={[0, 0.2, 0]}>
          <boxGeometry args={[0.22, 0.04, 0.03]} />
          <meshStandardMaterial
            color="#00ffff"
            emissive="#00ffff"
            emissiveIntensity={3.0}
            toneMapped={false}
          />
        </mesh>
        {/* Right eye glowing slit */}
        <mesh position={[0.16, 0.05, 0.42]} rotation={[0, -0.2, 0]}>
          <boxGeometry args={[0.22, 0.04, 0.03]} />
          <meshStandardMaterial
            color="#00ffff"
            emissive="#00ffff"
            emissiveIntensity={3.0}
            toneMapped={false}
          />
        </mesh>

        {/* Jaw / Chin plate */}
        <mesh position={[0, -0.28, 0.3]}>
          <boxGeometry args={[0.4, 0.15, 0.15]} />
          <meshStandardMaterial color="#08080c" metalness={0.95} roughness={0.1} />
        </mesh>
      </group>

      {/* ==================== LEGS ==================== */}
      <mesh position={[-0.3, -1.1, 0]} castShadow>
        <cylinderGeometry args={[0.18, 0.15, 0.9, 16]} />
        <meshStandardMaterial color="#0a0a10" metalness={0.9} roughness={0.2} />
      </mesh>
      <mesh position={[0.3, -1.1, 0]} castShadow>
        <cylinderGeometry args={[0.18, 0.15, 0.9, 16]} />
        <meshStandardMaterial color="#0a0a10" metalness={0.9} roughness={0.2} />
      </mesh>

      {/* Shins & boots */}
      <mesh position={[-0.3, -1.8, 0.05]} castShadow>
        <boxGeometry args={[0.28, 0.6, 0.35]} />
        <meshStandardMaterial color="#12121a" metalness={0.92} roughness={0.18} />
      </mesh>
      <mesh position={[0.3, -1.8, 0.05]} castShadow>
        <boxGeometry args={[0.28, 0.6, 0.35]} />
        <meshStandardMaterial color="#12121a" metalness={0.92} roughness={0.18} />
      </mesh>
    </group>
  )
}
