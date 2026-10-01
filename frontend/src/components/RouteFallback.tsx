export function RouteFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{ display: 'grid', placeItems: 'center', minHeight: '60vh', opacity: 0.7 }}
    >
      Loading…
    </div>
  )
}
