import type { ReactNode } from 'react'
import type { AppIcon } from './DroneIcon'

/**
 * Reusable KPI card. Values must come from the parent — never computed here.
 */
export function KpiCard({
  icon: Icon,
  label,
  value,
  supporting,
  trend,
  accent = 'auto',
  action,
}: {
  icon?: AppIcon
  label: string
  value: ReactNode
  supporting?: ReactNode
  trend?: ReactNode
  accent?: 'auto' | 'navy' | 'cyan' | 'green' | 'orange' | 'purple' | 'red'
  action?: ReactNode
}) {
  const tone = accent === 'auto' ? 'navy' : accent
  return (
    <article className={`stat-card tone-${tone} nk-anim-in`}>
      {Icon && (
        <div className="stat-icon">
          <Icon size={22} />
        </div>
      )}
      <div style={{ minWidth: 0 }}>
        <p>{label}</p>
        <strong>{value}</strong>
        {trend && <small className="nk-kpi-trend">{trend}</small>}
        {supporting && <small>{supporting}</small>}
        {action && <div className="nk-kpi-action">{action}</div>}
      </div>
    </article>
  )
}
