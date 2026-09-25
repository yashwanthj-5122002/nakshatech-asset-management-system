import type { ReactNode } from 'react'
import { CommandCenterHero } from './CommandCenterHero'
import type { AppIcon } from './DroneIcon'

/**
 * Page archetype wrappers. Presentation only — children keep all existing
 * data fetching, filters, tables and actions unchanged.
 */

export function CommandCenterPage({
  kicker,
  title,
  description,
  actions,
  heroKpis,
  children,
}: {
  kicker?: string
  title: string
  description?: string
  actions?: ReactNode
  heroKpis?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="nk-arch-command">
      <CommandCenterHero kicker={kicker} title={title} description={description} actions={actions}>
        {heroKpis && <div className="nk-hero-kpis">{heroKpis}</div>}
      </CommandCenterHero>
      {children}
    </div>
  )
}

export function OperationalDashboardPage({
  eyebrow,
  title,
  description,
  icon,
  actions,
  summary,
  meta,
  children,
}: {
  eyebrow?: string
  title: string
  description?: string
  icon?: AppIcon
  actions?: ReactNode
  /** KPI / stat strip rendered directly under the department identity header. */
  summary?: ReactNode
  /** Small context chips (period, team, live status) under the summary. */
  meta?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="nk-arch-ops nk-arch-command">
      <CommandCenterHero kicker={eyebrow} title={title} description={description} icon={icon} actions={actions} />
      {summary && <div className="nk-ops-summary nk-anim-in">{summary}</div>}
      {meta && <div className="nk-ops-meta nk-anim-in">{meta}</div>}
      {children}
    </div>
  )
}

export function WorkbenchPage({
  eyebrow,
  title,
  description,
  actions,
  summary,
  meta,
  children,
}: {
  /** Small identity chip rendered above the workbench title. */
  eyebrow?: ReactNode
  title: string
  description?: ReactNode
  actions?: ReactNode
  /** Optional compact KPI row under the workbench title. */
  summary?: ReactNode
  /** Small context chips (period, scope, status) under the workbench title. */
  meta?: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="nk-arch-workbench nk-arch-command">
      <CommandCenterHero kicker={eyebrow} title={title} description={description} actions={actions} />
      {meta && <div className="nk-ops-meta nk-anim-in">{meta}</div>}
      {summary && <div className="nk-wb-summary nk-anim-in">{summary}</div>}
      {children}
    </div>
  )
}
