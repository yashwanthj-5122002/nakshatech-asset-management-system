import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import type { AppIcon } from './DroneIcon'

/**
 * Scroll-reveal observer. Marks [data-nk-reveal] descendants visible once,
 * then disconnects. Uses classList directly — no React state per scroll.
 * Safe fallback: if IntersectionObserver is unavailable everything is shown.
 */
export function useNkReveal(rootRef: RefObject<HTMLElement | null>, enabled = true) {
  useEffect(() => {
    if (!enabled) return
    const root = rootRef.current
    if (!root) return
    const targets = Array.from(root.querySelectorAll<HTMLElement>('[data-nk-reveal]'))
    if (targets.length === 0) return
    if (typeof IntersectionObserver === 'undefined') {
      targets.forEach(el => el.classList.add('is-visible'))
      return
    }
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        }
      }
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.05 })
    targets.forEach(el => observer.observe(el))
    return () => observer.disconnect()
  }, [rootRef, enabled])
}

/**
 * Premium command-center hero. Full landing hero that smoothly compresses
 * into a sticky compact command bar on scroll (IntersectionObserver sentinel).
 * Presentation only — receives data/actions from the page.
 */
export function CommandCenterHero({
  id,
  kicker,
  title,
  description,
  icon: Icon,
  liveTitle,
  liveNote,
  actions,
  children,
}: {
  id?: string
  kicker?: ReactNode
  title: string
  description?: ReactNode
  icon?: AppIcon
  liveTitle?: string
  liveNote?: string
  actions?: ReactNode
  children?: ReactNode
}) {
  const [collapsed, setCollapsed] = useState(false)
  const sentinelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      ([entry]) => setCollapsed(!entry.isIntersecting),
      { rootMargin: '-72px 0px 0px 0px', threshold: 0 },
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [])

  return (
    <>
      <div className="nk-command-sentinel" ref={sentinelRef} aria-hidden="true" />
      <section
        className={`nk-hero nk-anim-in${collapsed ? ' is-collapsed' : ''}`}
        aria-label={`${typeof title === 'string' ? title : 'Page'} header`}
      >
        <div className="nk-hero-inner">
          <div className="nk-hero-copy">
            {kicker && (
              <div className="nk-hero-fold nk-hero-fold-top">
                <span className="nk-hero-kicker">{kicker}</span>
              </div>
            )}
            <div className="nk-hero-title-row">
              {Icon && (
                <span className="nk-hero-title-icon" aria-hidden="true">
                  <Icon size={20} />
                </span>
              )}
              <h1 id={id}>{title}</h1>
            </div>
            {description && (
              <div className="nk-hero-fold nk-hero-fold-bottom">
                <p>{description}</p>
              </div>
            )}
          </div>
          <div className="nk-hero-actions">
            {liveTitle && (
              <div className="nk-hero-live">
                <span className="nk-hero-live-dot" aria-hidden="true" />
                <div>
                  <strong>{liveTitle}</strong>
                  {liveNote && <small>{liveNote}</small>}
                </div>
              </div>
            )}
            {actions}
          </div>
        </div>
        {children}
      </section>
    </>
  )
}
