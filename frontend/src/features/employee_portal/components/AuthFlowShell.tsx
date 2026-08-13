import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { LoginNetworkMotionCanvas } from '../../../components/LoginNetworkMotionCanvas'
import '../../../login-interactive.css'

export function AuthFlowShell({
  eyebrow,
  title,
  description,
  children,
  backTo = '/login',
  backLabel = 'Back to login',
  onBack,
}: {
  eyebrow: string
  title: string
  description: string
  children: ReactNode
  backTo?: string
  backLabel?: string
  onBack?: () => void
}) {
  return (
    <main className="final-login-screen auth-flow-screen">
      <div className="final-login-shell">
        <LoginNetworkMotionCanvas />
        <header className="final-login-header">
          <Link className="final-login-brand" to="/" aria-label="NakshaTech Asset Management home">
            <img src="/nakshatech-horizontal-light.png" alt="NakshaTech" />
            <span className="final-login-brand-divider" aria-hidden="true" />
            <span className="final-login-product-name">Asset Management System</span>
          </Link>
        </header>
        <section className="final-login-copy">
          <h1><span>Smart Internal</span><strong>Employee Support</strong></h1>
          <span className="final-login-copy-rule" aria-hidden="true" />
          <p>Verified organization access, secure phone authenticator, branch-aware support tickets, and transparent resolution tracking.</p>
        </section>
        <section className="final-login-panel-zone">
          <div className="final-login-panel auth-flow-panel">
            {onBack ? (
              <button className="final-login-back auth-flow-back-button" type="button" onClick={onBack}>
                <ArrowLeft size={17} aria-hidden="true" />
                <span>{backLabel}</span>
              </button>
            ) : (
              <Link className="final-login-back" to={backTo}>
                <ArrowLeft size={17} aria-hidden="true" />
                <span>{backLabel}</span>
              </Link>
            )}
            <div className="final-login-heading">
              <span>{eyebrow}</span>
              <h2>{title}</h2>
              <p>{description}</p>
            </div>
            {children}
            <footer>© {new Date().getFullYear()} NakshaTech. All rights reserved.</footer>
          </div>
        </section>
      </div>
    </main>
  )
}
