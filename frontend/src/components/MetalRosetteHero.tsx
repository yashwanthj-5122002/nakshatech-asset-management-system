import { lazy, Suspense, useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { Grid3X3, HardHat, Layers3, Move3D, Pause, Play, RotateCcw, Ruler, ScanLine } from 'lucide-react'
import type { AssetNodePosition } from './WelcomeAssetScene'

const AssetScene = lazy(() => import('./WelcomeAssetScene'))
const divisions = [
  { key: 'gis', label: 'GIS / Mobile Mapping', detail: 'Spatial intelligence and field capture', icon: Layers3, x: 50, y: 20 },
  { key: 'ortho', label: 'Laser Scanning', detail: 'High-accuracy 3D scanning', icon: ScanLine, x: 80, y: 32 },
  { key: 'drone', label: 'Software Team', detail: 'Software development and systems', icon: Grid3X3, x: 80, y: 66 },
  { key: 'survey', label: 'Photogrammetry & Survey', detail: 'Surveying and photogrammetric measurement', icon: Ruler, x: 50, y: 80 },
  { key: 'civil', label: 'Civil', detail: 'Civil engineering and infrastructure', icon: HardHat, x: 20, y: 66 },
  { key: 'lidar', label: 'LiDAR & Ortho', detail: 'Point clouds and orthophotography', icon: Layers3, x: 20, y: 32 },
]

function CubeFaces({ hub = false }: { hub?: boolean }) {
  return (
    <div className={`rosette-cube${hub ? ' rosette-cube--hub' : ''}`} aria-hidden="true">
      <div className="rosette-cube__face rosette-cube__face--front">
        {hub && <img className="rosette-cube__logo" src="/nakshatech-horizontal-light.png" alt="" />}
      </div>
      {['back', 'right', 'left', 'top', 'bottom'].map(face => <div key={face} className={`rosette-cube__face rosette-cube__face--${face}`} />)}
    </div>
  )
}

/** HTML controls follow the rendered 3D positions; CSS cubes provide a graphics fallback. */
export function MetalRosetteHero() {
  const heroRef = useRef<HTMLDivElement>(null)
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const [paused, setPaused] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const [highlighted, setHighlighted] = useState<string | null>(null)
  const [webgl, setWebgl] = useState(false)
  const [resetVersion, setResetVersion] = useState(0)
  const activeDivision = divisions.find(division => division.key === activeKey)
  const ActiveIcon = activeDivision?.icon ?? Layers3
  const project = useCallback((positions: AssetNodePosition[]) => {
    const scene = heroRef.current?.querySelector<HTMLElement>('.rosette-hero__scene')
    const width = scene?.clientWidth ?? 1
    const height = scene?.clientHeight ?? 1
    const occupied: { left: number; top: number; right: number; bottom: number }[] = []
    const sizes = Object.fromEntries(positions.map(({ key }) => {
      const button = buttonRefs.current[key]
      return [key, { width: button?.offsetWidth ?? 0, height: button?.offsetHeight ?? 0 }]
    }))
    const ordered = [...positions].sort((a, b) => {
      if (buttonRefs.current[a.key] === document.activeElement) return -1
      if (buttonRefs.current[b.key] === document.activeElement) return 1
      return (a.depth ?? 0) - (b.depth ?? 0)
    })
    ordered.forEach(({ key, x, y, opacity = 1 }) => {
      const button = buttonRefs.current[key]
      if (!button) return
      const box = { left: x / 100 * width - sizes[key].width / 2, top: y / 100 * height - sizes[key].height / 2,
        right: x / 100 * width + sizes[key].width / 2, bottom: y / 100 * height + sizes[key].height / 2 }
      const overlaps = occupied.some(other => box.left < other.right + 3 && box.right > other.left - 3 && box.top < other.bottom + 3 && box.bottom > other.top - 3)
      const visible = opacity > .02 && !overlaps && box.left >= 0 && box.top >= 0 && box.right <= width && box.bottom <= height
      if (visible) occupied.push(box)
      button.style.left = `${x}%`
      button.style.top = `${y}%`
      button.style.opacity = visible ? String(opacity) : '0'
      button.style.visibility = visible ? 'visible' : 'hidden'
      button.tabIndex = visible ? 0 : -1
      button.setAttribute('aria-hidden', String(!visible))
    })
  }, [])
  const ready = useCallback((supported: boolean) => {
    setWebgl(supported)
    if (!supported) project(divisions)
  }, [project])
  const select = useCallback((key: string) => setActiveKey(value => value === key ? null : key), [])

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => setReducedMotion(preference.matches)
    sync()
    preference.addEventListener('change', sync)
    return () => preference.removeEventListener('change', sync)
  }, [])
  useEffect(() => {
    const hero = heroRef.current
    if (!hero) return
    let visible = true
    const sync = () => hero.classList.toggle('rosette-hero--resting', !visible || document.hidden)
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync() })
    observer.observe(hero)
    document.addEventListener('visibilitychange', sync)
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', sync) }
  }, [])

  return (
    <div ref={heroRef} className={`rosette-hero${paused ? ' rosette-hero--paused' : ''}${webgl ? ' rosette-hero--webgl' : ''}`}>
      <div className="rosette-hero__scene" role="group" tabIndex={webgl ? 0 : undefined} aria-label={webgl ? 'Interactive 3D NakshaTech network. Drag or use arrow keys to rotate. Select a division to highlight it.' : 'NakshaTech network. Select a division to highlight it.'}>
        <Suspense fallback={null}><AssetScene paused={paused} reducedMotion={reducedMotion} selected={activeKey} highlighted={highlighted} resetVersion={resetVersion} onReady={ready} onProject={project} onHighlight={setHighlighted} onSelect={select} /></Suspense>
        <div className="rosette-hero__halo" aria-hidden="true" />
        <div className="rosette-hero__orbit rosette-hero__orbit--outer" aria-hidden="true" />
        <div className="rosette-hero__orbit rosette-hero__orbit--inner" aria-hidden="true" />
        <svg className="rosette-hero__connections" viewBox="0 0 600 600" fill="none" aria-hidden="true">
          {divisions.map(({ key, x, y }, index) => (
            <g key={key}>
              <path d={`M300 294 L${x * 6} ${y * 6}`} stroke="#1594c2" strokeOpacity=".45" />
              <path className="rosette-hero__signal" style={{ animationDelay: `${index * -.7}s` }} d={`M300 294 L${x * 6} ${y * 6}`} pathLength="100" stroke="#67e9ff" strokeWidth="1.5" strokeDasharray="4 96" />
            </g>
          ))}
        </svg>
        <div className="rosette-hero__hub" aria-hidden="true"><div className="rosette-hero__hub-float"><CubeFaces hub /></div></div>
        {divisions.map(({ key, label, detail, icon: Icon, x, y }, index) => (
          <button type="button" key={key} ref={button => { buttonRefs.current[key] = button }} className={`rosette-hero__division${activeKey === key ? ' rosette-hero__division--active' : ''}`} style={{
            left: `${x}%`, top: `${y}%`, '--division-delay': `${index * -1.2}s`,
          } as CSSProperties} aria-label={`Explore ${label}: ${detail}`} aria-pressed={activeKey === key} aria-controls="rosette-division-detail" onPointerEnter={() => setHighlighted(key)} onPointerLeave={() => setHighlighted(null)} onFocus={() => setHighlighted(key)} onBlur={() => setHighlighted(null)} onClick={() => setActiveKey(value => value === key ? null : key)}>
            <div className="rosette-hero__satellite"><CubeFaces /></div>
            <span className="rosette-hero__division-label"><Icon size={6} strokeWidth={1.6} aria-hidden="true" /><strong>{label}</strong></span>
          </button>
        ))}
      </div>
    
    </div>
  )
}
