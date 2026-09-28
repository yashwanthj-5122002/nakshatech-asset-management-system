import type { ReactNode } from 'react'

type DashboardHeaderProps = {
  eyebrow?: string
  title: string
  description: string
  actions?: ReactNode
  details?: ReactNode
  variant?: 'default' | 'compact'
}

export function DashboardHeader({ eyebrow, title, description, actions, details, variant = 'default' }: DashboardHeaderProps) {
  return (
    <header className={`page-header ${variant === 'compact' ? 'is-compact' : ''}`}>
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
