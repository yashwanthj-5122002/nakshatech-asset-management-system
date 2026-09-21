import type { ReactNode } from 'react'

export function DashboardHeader({ eyebrow, title, description, actions, details }: { eyebrow?: string; title: string; description: string; actions?: ReactNode; details?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        <p>{description}</p>
        {details && <div className="page-header-detail">{details}</div>}
      </div>
      <div className="header-actions">{actions}</div>
    </header>
  )
}
