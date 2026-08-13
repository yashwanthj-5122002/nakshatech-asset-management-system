type Route = {
  d: string
  reverse?: boolean
}

/*
 * These routes are aligned to the full-world terrain reference used by the
 * welcome page. The terrain already contains the faint network artwork; these
 * paths add only the LIVE travelling energy so the movement is obvious.
 */
const ROUTES: Route[] = [
  { d: 'M 42 34 C 49 26, 55 27, 59 30' },
  { d: 'M 39 41 C 48 29, 54 27, 59 30', reverse: true },
  { d: 'M 59 30 C 66 24, 72 24, 76 27' },
  { d: 'M 59 30 C 71 23, 82 28, 85 48', reverse: true },
  { d: 'M 59 30 C 64 35, 68 40, 70 46' },
  { d: 'M 59 30 C 58 40, 58 49, 57 56', reverse: true },
  { d: 'M 57 56 C 53 59, 50 63, 48 69' },
  { d: 'M 57 56 C 61 62, 63 68, 64 73', reverse: true },
  { d: 'M 70 46 C 75 48, 79 52, 82 57' },
  { d: 'M 82 57 C 84 58, 85 60, 86 61', reverse: true },
  { d: 'M 85 48 C 89 54, 92 62, 93 71' },
]
export function WelcomeGeoNetwork() {
  return (
    <div className="welcome-geo-network" aria-hidden="true">
      <svg className="welcome-network-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
        <defs>
          <linearGradient id="welcome-route-trace-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#0982c9" stopOpacity="0.08" />
            <stop offset="48%" stopColor="#20c8e7" stopOpacity="0.50" />
            <stop offset="100%" stopColor="#0a77da" stopOpacity="0.10" />
          </linearGradient>
          <linearGradient id="welcome-route-energy-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#16b8e8" stopOpacity="0.12" />
            <stop offset="34%" stopColor="#6ff6ff" stopOpacity="0.90" />
            <stop offset="50%" stopColor="#ffffff" stopOpacity="1" />
            <stop offset="66%" stopColor="#5ceeff" stopOpacity="0.96" />
            <stop offset="100%" stopColor="#0786e8" stopOpacity="0.12" />
          </linearGradient>
        </defs>

        <g className="welcome-network-routes">
          {ROUTES.map((route, index) => {
            const direction = route.reverse ? 'reverse' : 'normal'
            const duration = 2.15 + (index % 4) * 0.26
            return (
              <g key={route.d}>
                <path className="welcome-network-route-trace" d={route.d} pathLength="100" />
                <path
                  className="welcome-network-route-energy welcome-network-route-energy--glow"
                  d={route.d}
                  pathLength="100"
                  style={{
                    animationDelay: `${index * -0.23}s`,
                    animationDuration: `${duration}s`,
                    animationDirection: direction,
                  }}
                />
                <path
                  className="welcome-network-route-energy welcome-network-route-energy--core"
                  d={route.d}
                  pathLength="100"
                  style={{
                    animationDelay: `${index * -0.23}s`,
                    animationDuration: `${duration}s`,
                    animationDirection: direction,
                  }}
                />
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
}
