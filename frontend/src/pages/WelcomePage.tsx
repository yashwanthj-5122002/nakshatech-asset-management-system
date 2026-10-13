import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { MetalRosetteHero } from '../components/MetalRosetteHero'
import { LoginParticleField } from '../components/LoginParticleField'

import './welcome-space.css'

export function WelcomePage() {
  return (
    <main className="space-welcome">
      <a className="space-welcome__skip" href="#workspace-welcome">Skip to content</a>
      <div className="space-welcome__background" aria-hidden="true" />
      <LoginParticleField />

      <div className="space-welcome__layout">
        <header className="space-welcome__header">
          <Link className="space-welcome__brand" to="/" aria-label="NakshaTech home">
            <img src="/nakshatech-horizontal-light.png" alt="NakshaTech" width="500" height="88" />
            <span className="space-welcome__brand-divider" aria-hidden="true" />
            <span className="space-welcome__product-name">Asset Management System</span>
          </Link>

        </header>

        <section className="space-welcome__hero" id="workspace-welcome" aria-labelledby="space-welcome-title" tabIndex={-1}>
          <div className="space-welcome__copy">
            <div className="space-welcome__eyebrow">Intelligent Asset Operations <span aria-hidden="true" /></div>

            <h1 id="space-welcome-title">
              <span>Organization</span>
              <strong className="space-welcome__title-gradient">Improvement Process</strong>
            </h1>

            <p className="space-welcome__description">
              Manage IT assets, drone operations, and workflows<br className="space-welcome__description-break" /> in one intelligent platform.
            </p>

            <Link className="space-welcome__login" to="/login">
              <span>Login</span><span className="space-welcome__login-arrow"><ArrowRight size={21} aria-hidden="true" /></span>
            </Link>
          </div>

          <div className="space-welcome__visual">
            <MetalRosetteHero />
          </div>
        </section>

      </div>
    </main>
  )
}
