import type { KeyboardEvent } from 'react'
import type { AppIcon } from './DroneIcon'

export function StatCard({
  icon: Icon,
  label,
  value,
  note,
  tone = 'blue',
  onClick,
  active = false,
}: {
  icon: AppIcon
  label: string
  value: number | string
  note?: string
  tone?: string
  onClick?: () => void
  active?: boolean
}) {
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (!onClick) return
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onClick()
    }
  }

  return (
    <article
      className={`stat-card tone-${tone} ${onClick ? 'interactive-stat-card' : ''} ${active ? 'active' : ''}`}
      onClick={onClick}
      onKeyDown={onKeyDown}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      aria-label={onClick ? `Open ${label} details` : undefined}
    >
      <div className="stat-icon"><Icon size={22} /></div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        {note && <small>{note}</small>}
      </div>
    </article>
  )
}
