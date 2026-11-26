import type { ReactNode } from 'react'
import { OperationalDashboardPage, WorkbenchPage } from './page-archetypes'
import type { AppIcon } from './DroneIcon'

type HeaderVariant = 'workbench' | 'ops'

/**
 * Shared page header. Default variant is a compact workbench/register title.
 * `variant="ops"` uses the operational dashboard header. Presentation only.
 */
export function DashboardHeader({
  eyebrow,
  title,
  description,
  icon,
  actions,
  details,
  summary,
  meta,
  variant = 'workbench',
}: {
  eyebrow?: string
  title: string
  description: string
  icon?: AppIcon
  actions?: ReactNode
  details?: ReactNode
  summary?: ReactNode
  meta?: ReactNode
  variant?: HeaderVariant
}) {
  if (variant === 'ops') {
    return (
      <OperationalDashboardPage
        eyebrow={eyebrow}
        title={title}
        description={description}
        icon={icon}
        actions={actions}
        summary={summary}
        meta={meta}
      >
        {details && <div className="page-header-detail">{details}</div>}
      </OperationalDashboardPage>
    )
  }

  return (
    <WorkbenchPage
      eyebrow={eyebrow}
      title={title}
      description={description}
      actions={actions}
      summary={summary}
      meta={meta}
    >
      {details && <div className="page-header-detail" style={{ marginTop: 8 }}>{details}</div>}
    </WorkbenchPage>
  )
}
