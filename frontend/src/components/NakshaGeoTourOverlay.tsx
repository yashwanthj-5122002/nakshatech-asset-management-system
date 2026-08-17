import { NakshaBengaluruNetworkGlobe } from './NakshaBengaluruNetworkGlobe'
import { LoginParticleField } from './LoginParticleField'
import '../login-geo-tour.css'

export function NakshaGeoTourOverlay({ onComplete: _onComplete }: { onComplete: () => void }) {
  return (
    <div className="naksha-geo-tour naksha-particle-globe is-ready" aria-hidden="true">
      <LoginParticleField />
      <div className="naksha-particle-globe-haze" />
      <NakshaBengaluruNetworkGlobe />
    </div>
  )
}
