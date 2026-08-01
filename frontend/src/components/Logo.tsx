export function Logo({ inverse = false, compact = false }: { inverse?: boolean; compact?: boolean }) {
  return (
    <div className={`logo-lockup ${inverse ? 'inverse' : ''} ${compact ? 'compact' : ''}`}>
      <img src="/nakshatech-logo.png" alt="NakshaTech" />
      {!compact && <span className="logo-divider" />}
      {!compact && <strong>ASSET MANAGEMENT SYSTEM</strong>}
    </div>
  )
}
