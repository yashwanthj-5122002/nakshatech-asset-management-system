import { ArrowRight, LogIn } from 'lucide-react'
import { Link } from 'react-router-dom'
import { WelcomeGeoNetwork } from '../components/WelcomeGeoNetwork'
import '../welcome-geospatial-network.css'

export function WelcomePage() {
  return (
    <main className="welcome-screen">
      <div className="welcome-shell welcome-shell--reference2">
        <div className="welcome-terrain-layer" aria-hidden="true" />
        <WelcomeGeoNetwork />
        <header className="welcome-header">
          <Link className="welcome-brand" to="/" aria-label="NakshaTech Asset Management System home">
            <img src="/nakshatech-horizontal-light.png" alt="NakshaTech" />
            <span className="welcome-brand-divider" aria-hidden="true" />
            <span className="welcome-product-name">Asset Management System</span>
          </Link>

          <div className="welcome-header-actions">
            <Link className="outline-login" to="/login" aria-label="Open privileged login page">
              <span>Login</span>
            </Link>
          </div>
        </header>

        <section className="welcome-main" aria-labelledby="welcome-title">
          <div className="welcome-copy">
            <h1 id="welcome-title">
              <span className="welcome-title-primary">Smart Internal</span>
              <span className="welcome-title-gradient">Asset Management</span>
            </h1>

            <p className="welcome-description">
              Manage IT assets, drone operations, workflows, and admin visibility — all in one intelligent platform.
            </p>

            <div className="welcome-login-actions">
              <Link className="welcome-login" to="/login">
                <LogIn size={22} aria-hidden="true" />
                <span>Login</span>
                <ArrowRight className="welcome-login-arrow" size={20} aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>

        <div className="welcome-coordinate coordinate-north" aria-hidden="true">60°N</div>
        <div className="welcome-coordinate coordinate-south" aria-hidden="true">30°S</div>
        <div className="welcome-grid-dots" aria-hidden="true" />
      </div>
    </main>
  )
}
