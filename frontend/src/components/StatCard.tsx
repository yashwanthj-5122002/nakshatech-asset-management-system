import type { AppIcon } from './DroneIcon'

export function StatCard({ icon: Icon, label, value, note, tone = 'blue' }: { icon: AppIcon; label: string; value: number | string; note?: string; tone?: string }) {
  return (
    <article className={`stat-card tone-${tone}`}>
      <div className="stat-icon"><Icon size={22} /></div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        {note && <small>{note}</small>}
      </div>
    </article>
  )
}
