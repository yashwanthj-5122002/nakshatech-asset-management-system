import {
  ChevronLeft,
  Globe2,
  LoaderCircle,
  MapPin,
  RotateCcw,
} from 'lucide-react'
import {
  Component,
  type ErrorInfo,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import { feature as topojsonFeature } from 'topojson-client'
import worldAtlas from 'world-atlas/countries-110m.json'

type PolygonGeometry = {
  type: 'Polygon' | 'MultiPolygon'
  coordinates: unknown
}

type BaseGeoFeature = {
  type: 'Feature'
  id?: string | number
  properties?: Record<string, unknown>
  geometry: PolygonGeometry
}

type MapPolygon = BaseGeoFeature & {
  __layer: 'country' | 'state'
  displayName: string
  iso3?: string
}

type CityPoint = {
  name: string
  lat: number
  lng: number
  countryIso3: string
  stateName: string
  population: number
  scalerank: number
  featureClass: string
}

type GlobePov = {
  lat: number
  lng: number
  altitude: number
}

type GeoFeatureCollection = {
  type: 'FeatureCollection'
  features: BaseGeoFeature[]
}

type GeoBoundaryMetadata = {
  boundarySource?: string
  boundaryLicense?: string
  simplifiedGeometryGeoJSON?: string
}

type DataStatus = 'idle' | 'loading' | 'ready' | 'unavailable'

type PointerGesture = {
  pointerId: number
  startX: number
  startY: number
  dragging: boolean
}

const PASSIVE_CURSOR_MAX_LNG = 9
const PASSIVE_CURSOR_MAX_LAT = 4.5
const POINTER_DRAG_THRESHOLD_PX = 6
const DRAG_CLICK_SUPPRESSION_MS = 260

const DEFAULT_POV: GlobePov = { lat: 18, lng: 58, altitude: 1.56 }
const MOBILE_POV: GlobePov = { lat: 17, lng: 66, altitude: 2.18 }
const CITY_DATA_SOURCES = [
  'https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/geojson/ne_50m_populated_places_simple.geojson',
  'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_50m_populated_places_simple.geojson',
]

// World Atlas uses ISO-3166 numeric IDs. This map keeps ADM1 requests local to
// the selected country without changing any authentication or CRM behavior.
const NUMERIC_TO_ISO3: Record<string, string> = {
  '004': 'AFG',
  '008': 'ALB',
  '010': 'ATA',
  '012': 'DZA',
  '016': 'ASM',
  '020': 'AND',
  '024': 'AGO',
  '028': 'ATG',
  '031': 'AZE',
  '032': 'ARG',
  '036': 'AUS',
  '040': 'AUT',
  '044': 'BHS',
  '048': 'BHR',
  '050': 'BGD',
  '051': 'ARM',
  '052': 'BRB',
  '056': 'BEL',
  '060': 'BMU',
  '064': 'BTN',
  '068': 'BOL',
  '070': 'BIH',
  '072': 'BWA',
  '074': 'BVT',
  '076': 'BRA',
  '084': 'BLZ',
  '086': 'IOT',
  '090': 'SLB',
  '092': 'VGB',
  '096': 'BRN',
  '100': 'BGR',
  '104': 'MMR',
  '108': 'BDI',
  '112': 'BLR',
  '116': 'KHM',
  '120': 'CMR',
  '124': 'CAN',
  '132': 'CPV',
  '136': 'CYM',
  '140': 'CAF',
  '144': 'LKA',
  '148': 'TCD',
  '152': 'CHL',
  '156': 'CHN',
  '158': 'TWN',
  '162': 'CXR',
  '166': 'CCK',
  '170': 'COL',
  '174': 'COM',
  '175': 'MYT',
  '178': 'COG',
  '180': 'COD',
  '184': 'COK',
  '188': 'CRI',
  '191': 'HRV',
  '192': 'CUB',
  '196': 'CYP',
  '203': 'CZE',
  '204': 'BEN',
  '208': 'DNK',
  '212': 'DMA',
  '214': 'DOM',
  '218': 'ECU',
  '222': 'SLV',
  '226': 'GNQ',
  '231': 'ETH',
  '232': 'ERI',
  '233': 'EST',
  '234': 'FRO',
  '238': 'FLK',
  '239': 'SGS',
  '242': 'FJI',
  '246': 'FIN',
  '248': 'ALA',
  '250': 'FRA',
  '254': 'GUF',
  '258': 'PYF',
  '260': 'ATF',
  '262': 'DJI',
  '266': 'GAB',
  '268': 'GEO',
  '270': 'GMB',
  '275': 'PSE',
  '276': 'DEU',
  '288': 'GHA',
  '292': 'GIB',
  '296': 'KIR',
  '300': 'GRC',
  '304': 'GRL',
  '308': 'GRD',
  '312': 'GLP',
  '316': 'GUM',
  '320': 'GTM',
  '324': 'GIN',
  '328': 'GUY',
  '332': 'HTI',
  '334': 'HMD',
  '336': 'VAT',
  '340': 'HND',
  '344': 'HKG',
  '348': 'HUN',
  '352': 'ISL',
  '356': 'IND',
  '360': 'IDN',
  '364': 'IRN',
  '368': 'IRQ',
  '372': 'IRL',
  '376': 'ISR',
  '380': 'ITA',
  '384': 'CIV',
  '388': 'JAM',
  '392': 'JPN',
  '398': 'KAZ',
  '400': 'JOR',
  '404': 'KEN',
  '408': 'PRK',
  '410': 'KOR',
  '414': 'KWT',
  '417': 'KGZ',
  '418': 'LAO',
  '422': 'LBN',
  '426': 'LSO',
  '428': 'LVA',
  '430': 'LBR',
  '434': 'LBY',
  '438': 'LIE',
  '440': 'LTU',
  '442': 'LUX',
  '446': 'MAC',
  '450': 'MDG',
  '454': 'MWI',
  '458': 'MYS',
  '462': 'MDV',
  '466': 'MLI',
  '470': 'MLT',
  '474': 'MTQ',
  '478': 'MRT',
  '480': 'MUS',
  '484': 'MEX',
  '492': 'MCO',
  '496': 'MNG',
  '498': 'MDA',
  '499': 'MNE',
  '500': 'MSR',
  '504': 'MAR',
  '508': 'MOZ',
  '512': 'OMN',
  '516': 'NAM',
  '520': 'NRU',
  '524': 'NPL',
  '528': 'NLD',
  '531': 'CUW',
  '533': 'ABW',
  '534': 'SXM',
  '535': 'BES',
  '540': 'NCL',
  '548': 'VUT',
  '554': 'NZL',
  '558': 'NIC',
  '562': 'NER',
  '566': 'NGA',
  '570': 'NIU',
  '574': 'NFK',
  '578': 'NOR',
  '580': 'MNP',
  '581': 'UMI',
  '583': 'FSM',
  '584': 'MHL',
  '585': 'PLW',
  '586': 'PAK',
  '591': 'PAN',
  '598': 'PNG',
  '600': 'PRY',
  '604': 'PER',
  '608': 'PHL',
  '612': 'PCN',
  '616': 'POL',
  '620': 'PRT',
  '624': 'GNB',
  '626': 'TLS',
  '630': 'PRI',
  '634': 'QAT',
  '638': 'REU',
  '642': 'ROU',
  '643': 'RUS',
  '646': 'RWA',
  '652': 'BLM',
  '654': 'SHN',
  '659': 'KNA',
  '660': 'AIA',
  '662': 'LCA',
  '663': 'MAF',
  '666': 'SPM',
  '670': 'VCT',
  '674': 'SMR',
  '678': 'STP',
  '682': 'SAU',
  '686': 'SEN',
  '688': 'SRB',
  '690': 'SYC',
  '694': 'SLE',
  '702': 'SGP',
  '703': 'SVK',
  '704': 'VNM',
  '705': 'SVN',
  '706': 'SOM',
  '710': 'ZAF',
  '716': 'ZWE',
  '724': 'ESP',
  '728': 'SSD',
  '729': 'SDN',
  '732': 'ESH',
  '740': 'SUR',
  '744': 'SJM',
  '748': 'SWZ',
  '752': 'SWE',
  '756': 'CHE',
  '760': 'SYR',
  '762': 'TJK',
  '764': 'THA',
  '768': 'TGO',
  '772': 'TKL',
  '776': 'TON',
  '780': 'TTO',
  '784': 'ARE',
  '788': 'TUN',
  '792': 'TUR',
  '795': 'TKM',
  '796': 'TCA',
  '798': 'TUV',
  '800': 'UGA',
  '804': 'UKR',
  '807': 'MKD',
  '818': 'EGY',
  '826': 'GBR',
  '831': 'GGY',
  '832': 'JEY',
  '833': 'IMN',
  '834': 'TZA',
  '840': 'USA',
  '850': 'VIR',
  '854': 'BFA',
  '858': 'URY',
  '860': 'UZB',
  '862': 'VEN',
  '876': 'WLF',
  '882': 'WSM',
  '887': 'YEM',
  '894': 'ZMB',
}

const NETWORK_ARCS = [
  { startLat: 21.1, startLng: 78.0, endLat: 1.35, endLng: 103.82 },
  { startLat: 21.1, startLng: 78.0, endLat: 25.2, endLng: 55.27 },
  { startLat: 21.1, startLng: 78.0, endLat: 50.11, endLng: 8.68 },
  { startLat: 21.1, startLng: 78.0, endLat: -33.87, endLng: 151.21 },
]

function normalizeLongitude(value: number) {
  let longitude = value
  while (longitude > 180) longitude -= 360
  while (longitude < -180) longitude += 360
  return longitude
}

function shortestLongitudeDelta(from: number, to: number) {
  return normalizeLongitude(to - from)
}

function normalizeName(value: string) {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function collectCoordinates(value: unknown, output: Array<[number, number]>) {
  if (!Array.isArray(value)) return
  if (
    value.length >= 2 &&
    typeof value[0] === 'number' &&
    typeof value[1] === 'number'
  ) {
    output.push([value[0], value[1]])
    return
  }
  for (const child of value) collectCoordinates(child, output)
}

function polygonFocus(feature: MapPolygon) {
  const coordinates: Array<[number, number]> = []
  collectCoordinates(feature.geometry.coordinates, coordinates)
  if (!coordinates.length) return { lat: 0, lng: 0, span: 40 }

  const latitudes = coordinates.map((coordinate) => coordinate[1])
  const longitudes = coordinates.map((coordinate) => normalizeLongitude(coordinate[0]))
  const shiftedLongitudes = longitudes.map((longitude) => (longitude < 0 ? longitude + 360 : longitude))

  const minLat = Math.min(...latitudes)
  const maxLat = Math.max(...latitudes)
  const minLng = Math.min(...longitudes)
  const maxLng = Math.max(...longitudes)
  const minShifted = Math.min(...shiftedLongitudes)
  const maxShifted = Math.max(...shiftedLongitudes)

  const normalSpan = maxLng - minLng
  const shiftedSpan = maxShifted - minShifted
  const useShifted = shiftedSpan < normalSpan
  const longitude = useShifted
    ? normalizeLongitude((minShifted + maxShifted) / 2)
    : (minLng + maxLng) / 2
  const longitudeSpan = useShifted ? shiftedSpan : normalSpan

  return {
    lat: (minLat + maxLat) / 2,
    lng: longitude,
    span: Math.max(maxLat - minLat, longitudeSpan),
  }
}

function countryFocusPov(country: MapPolygon): GlobePov {
  const focus = polygonFocus(country)
  return {
    lat: Math.max(-68, Math.min(68, focus.lat)),
    lng: focus.lng,
    altitude: Math.max(0.92, Math.min(1.38, 0.86 + focus.span / 135)),
  }
}

function stateFocusPov(state: MapPolygon): GlobePov {
  const focus = polygonFocus(state)
  return {
    lat: Math.max(-72, Math.min(72, focus.lat)),
    lng: focus.lng,
    altitude: Math.max(0.62, Math.min(0.94, 0.58 + focus.span / 85)),
  }
}

async function fetchJson<T>(url: string, timeoutMs = 9000): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
      cache: 'force-cache',
    })
    if (!response.ok) throw new Error(`Request failed (${response.status})`)
    return await response.json() as T
  } finally {
    window.clearTimeout(timeout)
  }
}

async function fetchJsonWithFallback<T>(urls: string[]): Promise<T> {
  let lastError: unknown = new Error('No data source available')
  for (const url of urls) {
    try {
      return await fetchJson<T>(url)
    } catch (error) {
      lastError = error
    }
  }
  throw lastError
}

function isPolygonGeometry(geometry: BaseGeoFeature['geometry'] | undefined): geometry is PolygonGeometry {
  return geometry?.type === 'Polygon' || geometry?.type === 'MultiPolygon'
}

function cityMatchesState(city: CityPoint, state: MapPolygon | null) {
  if (!state) return true
  const cityState = normalizeName(city.stateName)
  const selectedState = normalizeName(state.displayName)
  if (!cityState || !selectedState) return false
  return cityState === selectedState || cityState.includes(selectedState) || selectedState.includes(cityState)
}

function countryId(feature: MapPolygon | null) {
  return feature ? `${feature.__layer}:${String(feature.id ?? feature.iso3 ?? feature.displayName)}` : ''
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function polygonLabel(feature: MapPolygon) {
  const label = escapeHtml(feature.displayName)
  return `<div style="padding:7px 9px;color:#ecfdff;background:rgba(2,16,30,.92);border:1px solid rgba(49,210,231,.42);border-radius:8px;font:600 12px/1.2 system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.35)">${label}</div>`
}

class GlobeVisualBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.warn('NakshaTech 3D globe unavailable; login remains active.', error, info)
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="naksha-login-globe-fallback" role="status">
          <Globe2 size={30} aria-hidden="true" />
          <strong>Interactive globe unavailable</strong>
          <span>The secure login form is still fully available.</span>
        </div>
      )
    }
    return this.props.children
  }
}

function NakshaInteractiveGlobeInner() {
  const globeRef = useRef<GlobeMethods>()
  const hostRef = useRef<HTMLDivElement | null>(null)
  const stateCacheRef = useRef(new Map<string, { features: MapPolygon[]; attribution: string }>())
  const cityCacheRef = useRef<CityPoint[] | null>(null)
  const selectionRequestRef = useRef(0)
  const resumeTimerRef = useRef<number | null>(null)
  const pointerAnchorPovRef = useRef<GlobePov | null>(null)
  const pointerTargetPovRef = useRef<GlobePov | null>(null)
  const passiveMotionActiveRef = useRef(false)
  const passiveReturningRef = useRef(false)
  const pointerInsideRef = useRef(false)
  const pointerGestureRef = useRef<PointerGesture | null>(null)
  const suppressClickUntilRef = useRef(0)
  const focusLockUntilRef = useRef(0)
  const latestPovRef = useRef<GlobePov>(DEFAULT_POV)

  const [dimensions, setDimensions] = useState({ width: 640, height: 640 })
  const [ready, setReady] = useState(false)
  const [coarsePointer, setCoarsePointer] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [hoveredPolygon, setHoveredPolygon] = useState<MapPolygon | null>(null)
  const [selectedCountry, setSelectedCountry] = useState<MapPolygon | null>(null)
  const [selectedState, setSelectedState] = useState<MapPolygon | null>(null)
  const [selectedCity, setSelectedCity] = useState<CityPoint | null>(null)
  const [stateFeatures, setStateFeatures] = useState<MapPolygon[]>([])
  const [allCities, setAllCities] = useState<CityPoint[]>([])
  const [stateStatus, setStateStatus] = useState<DataStatus>('idle')
  const [cityStatus, setCityStatus] = useState<DataStatus>('idle')
  const [stateAttribution, setStateAttribution] = useState('')
  const [currentAltitude, setCurrentAltitude] = useState(DEFAULT_POV.altitude)

  const countries = useMemo<MapPolygon[]>(() => {
    const topology = worldAtlas as unknown as { objects: { countries: unknown } }
    const collection = topojsonFeature(
      worldAtlas as never,
      topology.objects.countries as never,
    ) as unknown as GeoFeatureCollection

    return collection.features
      .filter((item) => isPolygonGeometry(item.geometry))
      .map((item) => {
        const numericId = String(item.id ?? '').padStart(3, '0')
        return {
          ...item,
          __layer: 'country' as const,
          displayName: String(item.properties?.name ?? 'Country'),
          iso3: NUMERIC_TO_ISO3[numericId],
        }
      })
  }, [])

  const polygons = useMemo(
    () => selectedCountry && stateFeatures.length ? [...countries, ...stateFeatures] : countries,
    [countries, selectedCountry, stateFeatures],
  )

  const visibleCities = useMemo(() => {
    if (!selectedCountry?.iso3 || currentAltitude > 1.33) return []
    const matching = allCities
      .filter((city) => city.countryIso3 === selectedCountry.iso3 && cityMatchesState(city, selectedState))
      .sort((a, b) => {
        const capitalA = a.featureClass.toLowerCase().includes('capital') ? 1 : 0
        const capitalB = b.featureClass.toLowerCase().includes('capital') ? 1 : 0
        if (capitalA !== capitalB) return capitalB - capitalA
        if (a.scalerank !== b.scalerank) return a.scalerank - b.scalerank
        return b.population - a.population
      })

    return matching.slice(0, selectedState ? 28 : 22)
  }, [allCities, currentAltitude, selectedCountry, selectedState])

  const visibleCityLabels = useMemo(
    () => currentAltitude <= (selectedState ? 0.92 : 0.82) ? visibleCities.slice(0, selectedState ? 18 : 12) : [],
    [currentAltitude, selectedState, visibleCities],
  )

  const clearResumeTimer = useCallback(() => {
    if (resumeTimerRef.current !== null) {
      window.clearTimeout(resumeTimerRef.current)
      resumeTimerRef.current = null
    }
  }, [])

  const setAutoRotate = useCallback((enabled: boolean) => {
    const controls = globeRef.current?.controls()
    if (!controls) return
    controls.autoRotate = enabled && !reducedMotion && !coarsePointer && !selectedCountry
  }, [coarsePointer, reducedMotion, selectedCountry])

  const scheduleAutoRotate = useCallback((delay = 650) => {
    clearResumeTimer()
    if (selectedCountry || reducedMotion || coarsePointer) return
    resumeTimerRef.current = window.setTimeout(() => setAutoRotate(true), delay)
  }, [clearResumeTimer, coarsePointer, reducedMotion, selectedCountry, setAutoRotate])

  const stopPassiveMotion = useCallback(() => {
    passiveMotionActiveRef.current = false
    passiveReturningRef.current = false
    pointerTargetPovRef.current = null
  }, [])

  const lockPassiveMotionFor = useCallback((duration: number) => {
    focusLockUntilRef.current = performance.now() + Math.max(0, duration) + 90
    stopPassiveMotion()
    pointerAnchorPovRef.current = null
  }, [stopPassiveMotion])

  const passiveMotionIsLocked = useCallback(() => performance.now() < focusLockUntilRef.current, [])

  const readCurrentPov = useCallback((): GlobePov => {
    const current = globeRef.current?.pointOfView() as GlobePov | undefined
    if (
      current &&
      Number.isFinite(current.lat) &&
      Number.isFinite(current.lng) &&
      Number.isFinite(current.altitude)
    ) {
      return { lat: current.lat, lng: normalizeLongitude(current.lng), altitude: current.altitude }
    }
    return { ...latestPovRef.current }
  }, [])

  const targetPovForPointer = useCallback((event: ReactPointerEvent<HTMLDivElement>, anchor: GlobePov) => {
    const host = hostRef.current
    if (!host) return anchor
    const rect = host.getBoundingClientRect()
    const rawX = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1
    const rawY = ((event.clientY - rect.top) / Math.max(1, rect.height)) * 2 - 1
    const nx = Math.abs(rawX) < 0.025 ? 0 : Math.max(-1, Math.min(1, rawX))
    const ny = Math.abs(rawY) < 0.025 ? 0 : Math.max(-1, Math.min(1, rawY))
    return {
      lat: Math.max(-68, Math.min(68, anchor.lat - ny * PASSIVE_CURSOR_MAX_LAT)),
      lng: normalizeLongitude(anchor.lng + nx * PASSIVE_CURSOR_MAX_LNG),
      altitude: anchor.altitude,
    }
  }, [])

  const focusCountry = useCallback((country: MapPolygon, duration = 850) => {
    const transitionMs = reducedMotion ? 0 : duration
    lockPassiveMotionFor(transitionMs)
    const pov = countryFocusPov(country)
    latestPovRef.current = pov
    globeRef.current?.pointOfView(pov, transitionMs)
  }, [lockPassiveMotionFor, reducedMotion])

  const focusState = useCallback((state: MapPolygon, duration = 760) => {
    const transitionMs = reducedMotion ? 0 : duration
    lockPassiveMotionFor(transitionMs)
    const pov = stateFocusPov(state)
    latestPovRef.current = pov
    globeRef.current?.pointOfView(pov, transitionMs)
  }, [lockPassiveMotionFor, reducedMotion])

  const focusCity = useCallback((city: CityPoint, duration = 650) => {
    const transitionMs = reducedMotion ? 0 : duration
    lockPassiveMotionFor(transitionMs)
    const pov = { lat: city.lat, lng: city.lng, altitude: 0.54 }
    latestPovRef.current = pov
    globeRef.current?.pointOfView(pov, transitionMs)
  }, [lockPassiveMotionFor, reducedMotion])

  const loadStatesForCountry = useCallback(async (country: MapPolygon, requestId: number) => {
    if (!country.iso3) {
      if (selectionRequestRef.current === requestId) setStateStatus('unavailable')
      return
    }

    const cached = stateCacheRef.current.get(country.iso3)
    if (cached) {
      if (selectionRequestRef.current === requestId) {
        setStateFeatures(cached.features)
        setStateAttribution(cached.attribution)
        setStateStatus(cached.features.length ? 'ready' : 'unavailable')
      }
      return
    }

    if (selectionRequestRef.current === requestId) setStateStatus('loading')
    try {
      const metadata = await fetchJson<GeoBoundaryMetadata>(
        `https://www.geoboundaries.org/api/current/gbOpen/${country.iso3}/ADM1/`,
      )
      if (!metadata.simplifiedGeometryGeoJSON) throw new Error('No simplified ADM1 geometry')
      const collection = await fetchJson<GeoFeatureCollection>(metadata.simplifiedGeometryGeoJSON, 12000)
      const features = collection.features
        .filter((item) => isPolygonGeometry(item.geometry))
        .map((item, index) => ({
          ...item,
          id: item.id ?? `${country.iso3}-ADM1-${index}`,
          __layer: 'state' as const,
          iso3: country.iso3,
          displayName: String(item.properties?.shapeName ?? item.properties?.name ?? `Region ${index + 1}`),
        }))

      const attribution = [metadata.boundarySource, metadata.boundaryLicense].filter(Boolean).join(' · ')
      stateCacheRef.current.set(country.iso3, { features, attribution })
      if (selectionRequestRef.current === requestId) {
        setStateFeatures(features)
        setStateAttribution(attribution)
        setStateStatus(features.length ? 'ready' : 'unavailable')
      }
    } catch {
      if (selectionRequestRef.current === requestId) {
        setStateFeatures([])
        setStateAttribution('')
        setStateStatus('unavailable')
      }
    }
  }, [])

  const loadCities = useCallback(async () => {
    if (cityCacheRef.current) {
      setAllCities(cityCacheRef.current)
      setCityStatus('ready')
      return
    }
    setCityStatus('loading')
    try {
      const collection = await fetchJsonWithFallback<{
        features: Array<{
          properties?: Record<string, unknown>
          geometry?: { type?: string; coordinates?: unknown }
        }>
      }>(CITY_DATA_SOURCES)

      const cities: CityPoint[] = []
      for (const item of collection.features) {
        if (item.geometry?.type !== 'Point' || !Array.isArray(item.geometry.coordinates)) continue
        const [lng, lat] = item.geometry.coordinates
        if (typeof lat !== 'number' || typeof lng !== 'number') continue
        const properties = item.properties ?? {}
        const scalerank = Number(properties.scalerank ?? 99)
        const featureClass = String(properties.featurecla ?? '')
        const isMajor =
          scalerank <= 4 ||
          featureClass.toLowerCase().includes('capital') ||
          Number(properties.worldcity ?? 0) === 1 ||
          Number(properties.megacity ?? 0) === 1
        if (!isMajor) continue
        const countryIso3 = String(properties.adm0_a3 ?? properties.sov_a3 ?? '')
        if (!countryIso3) continue
        cities.push({
          name: String(properties.name ?? properties.nameascii ?? 'City'),
          lat,
          lng,
          countryIso3,
          stateName: String(properties.adm1name ?? ''),
          population: Number(properties.pop_max ?? 0),
          scalerank,
          featureClass,
        })
      }

      cityCacheRef.current = cities
      setAllCities(cities)
      setCityStatus('ready')
    } catch {
      setCityStatus('unavailable')
    }
  }, [])

  const selectCountry = useCallback((country: MapPolygon) => {
    clearResumeTimer()
    stopPassiveMotion()
    const controls = globeRef.current?.controls()
    if (controls) controls.autoRotate = false
    pointerAnchorPovRef.current = null
    setSelectedCountry(country)
    setSelectedState(null)
    setSelectedCity(null)
    setHoveredPolygon(null)
    setStateFeatures([])
    setStateAttribution('')
    setStateStatus('idle')
    focusCountry(country)

    const requestId = selectionRequestRef.current + 1
    selectionRequestRef.current = requestId
    void loadStatesForCountry(country, requestId)
    void loadCities()
  }, [clearResumeTimer, focusCountry, loadCities, loadStatesForCountry, stopPassiveMotion])

  const selectState = useCallback((state: MapPolygon) => {
    setSelectedState(state)
    setSelectedCity(null)
    setHoveredPolygon(null)
    focusState(state)
  }, [focusState])

  const selectCity = useCallback((city: CityPoint) => {
    setSelectedCity(city)
    focusCity(city)
  }, [focusCity])

  const resetGlobe = useCallback(() => {
    selectionRequestRef.current += 1
    setSelectedCountry(null)
    setSelectedState(null)
    setSelectedCity(null)
    setHoveredPolygon(null)
    setStateFeatures([])
    setStateAttribution('')
    setStateStatus('idle')
    const transitionMs = reducedMotion ? 0 : 900
    lockPassiveMotionFor(transitionMs)
    const pov = coarsePointer ? MOBILE_POV : DEFAULT_POV
    latestPovRef.current = pov
    globeRef.current?.pointOfView(pov, transitionMs)
    clearResumeTimer()
    if (!reducedMotion && !coarsePointer) {
      resumeTimerRef.current = window.setTimeout(() => {
        const controls = globeRef.current?.controls()
        if (controls) controls.autoRotate = true
      }, 940)
    }
  }, [clearResumeTimer, coarsePointer, lockPassiveMotionFor, reducedMotion])

  const backOneLevel = useCallback(() => {
    if (selectedCity) {
      setSelectedCity(null)
      if (selectedState) focusState(selectedState)
      else if (selectedCountry) focusCountry(selectedCountry)
      return
    }
    if (selectedState) {
      setSelectedState(null)
      if (selectedCountry) focusCountry(selectedCountry)
    }
  }, [focusCountry, focusState, selectedCity, selectedCountry, selectedState])

  useEffect(() => {
    const host = hostRef.current
    if (!host || typeof window === 'undefined') return

    const pointerQuery = window.matchMedia('(pointer: coarse)')
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const syncPreferences = () => {
      setCoarsePointer(pointerQuery.matches)
      setReducedMotion(motionQuery.matches)
    }
    syncPreferences()

    const resize = () => {
      const rect = host.getBoundingClientRect()
      setDimensions({
        width: Math.max(260, Math.round(rect.width)),
        height: Math.max(260, Math.round(rect.height)),
      })
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(host)

    pointerQuery.addEventListener?.('change', syncPreferences)
    motionQuery.addEventListener?.('change', syncPreferences)
    return () => {
      observer.disconnect()
      pointerQuery.removeEventListener?.('change', syncPreferences)
      motionQuery.removeEventListener?.('change', syncPreferences)
    }
  }, [])

  useEffect(() => {
    if (!ready) return
    const globe = globeRef.current
    const controls = globe?.controls()
    if (!globe || !controls) return

    const radius = globe.getGlobeRadius()
    controls.enableDamping = true
    controls.dampingFactor = 0.075
    controls.enablePan = false
    controls.enableZoom = true
    controls.rotateSpeed = coarsePointer ? 0.42 : 0.34
    controls.zoomSpeed = coarsePointer ? 0.65 : 0.56
    controls.minDistance = radius * 1.34
    controls.maxDistance = radius * 4.4
    controls.autoRotateSpeed = 0.28
    controls.autoRotate = !reducedMotion && !coarsePointer && !selectedCountry

    if (!selectedCountry) {
      const pov = coarsePointer ? MOBILE_POV : DEFAULT_POV
      latestPovRef.current = pov
      globe.pointOfView(pov, reducedMotion ? 0 : 720)
    }
  }, [coarsePointer, ready, reducedMotion, selectedCountry])

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.hidden) globeRef.current?.pauseAnimation()
      else globeRef.current?.resumeAnimation()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => document.removeEventListener('visibilitychange', onVisibilityChange)
  }, [])

  useEffect(() => {
    if (!ready || coarsePointer || reducedMotion) return

    let animationFrame = 0
    let previousTime = performance.now()
    const animatePassiveMotion = (now: number) => {
      animationFrame = window.requestAnimationFrame(animatePassiveMotion)
      const frameMs = Math.max(1, Math.min(40, now - previousTime))
      previousTime = now

      if (
        document.hidden ||
        passiveMotionIsLocked() ||
        !passiveMotionActiveRef.current ||
        pointerGestureRef.current?.dragging
      ) return

      const globe = globeRef.current
      const target = pointerTargetPovRef.current
      if (!globe || !target) return

      const current = latestPovRef.current
      const blend = 1 - Math.pow(0.86, frameMs / 16.67)
      const lngDelta = shortestLongitudeDelta(current.lng, target.lng)
      const next: GlobePov = {
        lat: current.lat + (target.lat - current.lat) * blend,
        lng: normalizeLongitude(current.lng + lngDelta * blend),
        altitude: current.altitude + (target.altitude - current.altitude) * blend,
      }

      latestPovRef.current = next
      globe.pointOfView(next, 0)

      if (passiveReturningRef.current) {
        const settled =
          Math.abs(target.lat - next.lat) < 0.025 &&
          Math.abs(shortestLongitudeDelta(next.lng, target.lng)) < 0.035 &&
          Math.abs(target.altitude - next.altitude) < 0.002
        if (settled) {
          latestPovRef.current = { ...target }
          globe.pointOfView(target, 0)
          passiveMotionActiveRef.current = false
          passiveReturningRef.current = false
          pointerTargetPovRef.current = null
          scheduleAutoRotate(180)
        }
      }
    }

    animationFrame = window.requestAnimationFrame(animatePassiveMotion)
    return () => window.cancelAnimationFrame(animationFrame)
  }, [coarsePointer, passiveMotionIsLocked, ready, reducedMotion, scheduleAutoRotate])

  useEffect(() => () => {
    clearResumeTimer()
    stopPassiveMotion()
  }, [clearResumeTimer, stopPassiveMotion])

  const onPointerEnter = useCallback(() => {
    pointerInsideRef.current = true
    if (coarsePointer || reducedMotion || passiveMotionIsLocked() || pointerGestureRef.current) return
    clearResumeTimer()
    setAutoRotate(false)
    const current = readCurrentPov()
    latestPovRef.current = current
    pointerAnchorPovRef.current = current
    pointerTargetPovRef.current = current
    passiveReturningRef.current = false
    passiveMotionActiveRef.current = true
  }, [clearResumeTimer, coarsePointer, passiveMotionIsLocked, readCurrentPov, reducedMotion, setAutoRotate])

  const onPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = pointerGestureRef.current
    if (gesture && gesture.pointerId === event.pointerId && event.buttons !== 0) {
      if (!gesture.dragging) {
        const distance = Math.hypot(event.clientX - gesture.startX, event.clientY - gesture.startY)
        if (distance >= POINTER_DRAG_THRESHOLD_PX) {
          gesture.dragging = true
          suppressClickUntilRef.current = Number.POSITIVE_INFINITY
          stopPassiveMotion()
          pointerAnchorPovRef.current = null
        }
      }
      return
    }

    if (
      event.buttons !== 0 ||
      coarsePointer ||
      reducedMotion ||
      passiveMotionIsLocked() ||
      !pointerInsideRef.current
    ) return

    let anchor = pointerAnchorPovRef.current
    if (!anchor) {
      anchor = readCurrentPov()
      pointerAnchorPovRef.current = anchor
    }
    clearResumeTimer()
    setAutoRotate(false)
    pointerTargetPovRef.current = targetPovForPointer(event, anchor)
    passiveReturningRef.current = false
    passiveMotionActiveRef.current = true
  }, [
    clearResumeTimer,
    coarsePointer,
    passiveMotionIsLocked,
    readCurrentPov,
    reducedMotion,
    setAutoRotate,
    stopPassiveMotion,
    targetPovForPointer,
  ])

  const onPointerLeave = useCallback(() => {
    pointerInsideRef.current = false
    if (coarsePointer || reducedMotion || passiveMotionIsLocked() || pointerGestureRef.current?.dragging) return
    const anchor = pointerAnchorPovRef.current
    pointerAnchorPovRef.current = null
    if (!anchor) {
      stopPassiveMotion()
      scheduleAutoRotate(280)
      return
    }
    pointerTargetPovRef.current = anchor
    passiveReturningRef.current = true
    passiveMotionActiveRef.current = true
  }, [coarsePointer, passiveMotionIsLocked, reducedMotion, scheduleAutoRotate, stopPassiveMotion])

  const onPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    pointerGestureRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      dragging: false,
    }
    suppressClickUntilRef.current = 0
    stopPassiveMotion()
    pointerAnchorPovRef.current = null
    clearResumeTimer()
    setAutoRotate(false)
  }, [clearResumeTimer, setAutoRotate, stopPassiveMotion])

  const finishPointerGesture = useCallback((pointerId: number, cancelled = false) => {
    const gesture = pointerGestureRef.current
    if (!gesture || gesture.pointerId !== pointerId) return

    const dragged = gesture.dragging
    pointerGestureRef.current = null
    if (dragged || cancelled) {
      suppressClickUntilRef.current = performance.now() + DRAG_CLICK_SUPPRESSION_MS
    } else {
      suppressClickUntilRef.current = 0
    }

    const current = readCurrentPov()
    latestPovRef.current = current
    if (!cancelled) {
      if (pointerInsideRef.current) {
        pointerAnchorPovRef.current = current
        pointerTargetPovRef.current = current
        passiveReturningRef.current = false
        passiveMotionActiveRef.current = false
        if (!selectedCountry) scheduleAutoRotate(dragged ? 1200 : 900)
      } else {
        pointerAnchorPovRef.current = null
        stopPassiveMotion()
        if (!selectedCountry) scheduleAutoRotate(dragged ? 720 : 280)
      }
    }
  }, [readCurrentPov, scheduleAutoRotate, selectedCountry, stopPassiveMotion])

  useEffect(() => {
    const finishOutside = (event: PointerEvent) => finishPointerGesture(event.pointerId, event.type === 'pointercancel')
    window.addEventListener('pointerup', finishOutside, true)
    window.addEventListener('pointercancel', finishOutside, true)
    return () => {
      window.removeEventListener('pointerup', finishOutside, true)
      window.removeEventListener('pointercancel', finishOutside, true)
    }
  }, [finishPointerGesture])

  const onPointerUp = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    finishPointerGesture(event.pointerId)
  }, [finishPointerGesture])

  const onPointerCancel = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    finishPointerGesture(event.pointerId, true)
  }, [finishPointerGesture])

  const allowSelectionClick = useCallback(() => performance.now() >= suppressClickUntilRef.current, [])

  const polygonCapColor = useCallback((polygon: MapPolygon) => {
    if (polygon.__layer === 'state') {
      if (selectedState && countryId(polygon) === countryId(selectedState)) return 'rgba(14, 209, 232, 0.72)'
      if (hoveredPolygon && countryId(polygon) === countryId(hoveredPolygon)) return 'rgba(17, 188, 222, 0.58)'
      return 'rgba(8, 74, 105, 0.32)'
    }
    if (selectedCountry && countryId(polygon) === countryId(selectedCountry)) return 'rgba(9, 188, 220, 0.46)'
    if (hoveredPolygon && countryId(polygon) === countryId(hoveredPolygon)) return 'rgba(14, 158, 204, 0.45)'
    return 'rgba(5, 36, 62, 0.72)'
  }, [hoveredPolygon, selectedCountry, selectedState])

  const polygonStrokeColor = useCallback((polygon: MapPolygon) => {
    if (polygon.__layer === 'state') {
      return selectedState && countryId(polygon) === countryId(selectedState) ? '#73f2ff' : 'rgba(72, 209, 232, .58)'
    }
    if (selectedCountry && countryId(polygon) === countryId(selectedCountry)) return '#3ce7f6'
    if (hoveredPolygon && countryId(polygon) === countryId(hoveredPolygon)) return '#61edfa'
    return 'rgba(57, 156, 207, .45)'
  }, [hoveredPolygon, selectedCountry, selectedState])

  const polygonAltitude = useCallback((polygon: MapPolygon) => {
    if (polygon.__layer === 'state') {
      return selectedState && countryId(polygon) === countryId(selectedState) ? 0.018 : 0.011
    }
    if (selectedCountry && countryId(polygon) === countryId(selectedCountry)) return 0.008
    if (hoveredPolygon && countryId(polygon) === countryId(hoveredPolygon)) return 0.006
    return 0.0025
  }, [hoveredPolygon, selectedCountry, selectedState])

  const activeLabel = selectedCity?.name || selectedState?.displayName || selectedCountry?.displayName || hoveredPolygon?.displayName
  const detailMessage = selectedCountry
    ? stateStatus === 'loading'
      ? 'Loading states / provinces…'
      : stateStatus === 'unavailable'
        ? 'Country selected · state detail unavailable'
        : cityStatus === 'loading'
          ? 'Loading major cities…'
          : 'Scroll to zoom · select a state or city'
    : 'Move cursor to guide · drag to rotate · scroll to zoom'

  return (
    <div
      ref={hostRef}
      className="naksha-login-globe"
      aria-label="Interactive geographic globe"
      onPointerEnter={onPointerEnter}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
    >
      <div className="naksha-login-globe-stage" aria-hidden="true">
        <Globe
          ref={globeRef}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="rgba(0,0,0,0)"
          showAtmosphere
          atmosphereColor="#16c7e8"
          atmosphereAltitude={0.13}
          rendererConfig={{ antialias: !coarsePointer, alpha: true }}
          animateIn={!reducedMotion}
          polygonsData={polygons}
          polygonLabel={(polygon: unknown) => polygonLabel(polygon as MapPolygon)}
          polygonCapColor={(polygon: unknown) => polygonCapColor(polygon as MapPolygon)}
          polygonSideColor={() => 'rgba(2, 21, 38, .32)'}
          polygonStrokeColor={(polygon: unknown) => polygonStrokeColor(polygon as MapPolygon)}
          polygonAltitude={(polygon: unknown) => polygonAltitude(polygon as MapPolygon)}
          polygonCapCurvatureResolution={coarsePointer ? 7 : 4}
          polygonsTransitionDuration={reducedMotion ? 0 : 260}
          onPolygonHover={(polygon: unknown) => setHoveredPolygon((polygon as MapPolygon | null) ?? null)}
          onPolygonClick={(polygon: unknown) => {
            if (!allowSelectionClick()) return
            const feature = polygon as MapPolygon
            if (feature.__layer === 'state') selectState(feature)
            else selectCountry(feature)
          }}
          arcsData={selectedCountry ? [] : NETWORK_ARCS}
          arcColor={() => ['rgba(30,224,240,.88)', 'rgba(17,91,224,.42)']}
          arcStroke={0.055}
          arcAltitudeAutoScale={0.28}
          arcDashLength={0.22}
          arcDashGap={0.52}
          arcDashAnimateTime={reducedMotion ? 0 : 4400}
          arcsTransitionDuration={0}
          pointsData={visibleCities}
          pointLat="lat"
          pointLng="lng"
          pointLabel={(city: unknown) => String((city as CityPoint).name)}
          pointColor={(city: unknown) => selectedCity?.name === (city as CityPoint).name ? '#f2ffff' : '#45e3f1'}
          pointAltitude={0.012}
          pointRadius={(city: unknown) => (city as CityPoint).featureClass.toLowerCase().includes('capital') ? 0.22 : 0.15}
          pointResolution={coarsePointer ? 6 : 9}
          pointsTransitionDuration={reducedMotion ? 0 : 220}
          onPointClick={(city: unknown) => { if (allowSelectionClick()) selectCity(city as CityPoint) }}
          labelsData={visibleCityLabels}
          labelLat="lat"
          labelLng="lng"
          labelText="name"
          labelColor={() => 'rgba(219,250,255,.88)'}
          labelAltitude={0.018}
          labelSize={0.34}
          labelDotRadius={0.055}
          labelResolution={2}
          labelsTransitionDuration={reducedMotion ? 0 : 180}
          onLabelClick={(city: unknown) => { if (allowSelectionClick()) selectCity(city as CityPoint) }}
          onZoom={(pov: unknown) => {
            const next = { ...(pov as GlobePov), lng: normalizeLongitude((pov as GlobePov).lng) }
            latestPovRef.current = next
            if (passiveMotionActiveRef.current && !pointerGestureRef.current?.dragging) {
              if (pointerAnchorPovRef.current) pointerAnchorPovRef.current.altitude = next.altitude
              if (pointerTargetPovRef.current) pointerTargetPovRef.current.altitude = next.altitude
            }
            setCurrentAltitude((current) => Math.abs(current - next.altitude) > 0.01 ? next.altitude : current)
          }}
          onGlobeReady={() => setReady(true)}
          enablePointerInteraction
          showPointerCursor
        />
      </div>

      <div className="naksha-login-globe-chrome" aria-live="polite">
        <div className="naksha-login-globe-status">
          <span className="naksha-login-globe-pulse" aria-hidden="true" />
          <div>
            <strong>{activeLabel || 'Interactive World'}</strong>
            <small>{detailMessage}</small>
          </div>
        </div>

        {selectedCountry && (
          <div className="naksha-login-globe-actions">
            {(selectedState || selectedCity) && (
              <button type="button" onClick={backOneLevel}>
                <ChevronLeft size={15} aria-hidden="true" />
                {selectedCity ? (selectedState?.displayName || selectedCountry.displayName) : selectedCountry.displayName}
              </button>
            )}
            <button type="button" onClick={resetGlobe}>
              <RotateCcw size={15} aria-hidden="true" />
              Return to globe
            </button>
          </div>
        )}
      </div>

      {selectedCity && (
        <div className="naksha-login-globe-city-chip">
          <MapPin size={14} aria-hidden="true" />
          <span>{selectedCity.name}</span>
        </div>
      )}

      {(stateStatus === 'loading' || cityStatus === 'loading') && selectedCountry && (
        <LoaderCircle className="naksha-login-globe-loader" size={18} aria-hidden="true" />
      )}

      <div
        className="naksha-login-globe-source"
        title={stateAttribution || 'Country and city reference data: Natural Earth. State/province detail: geoBoundaries when available.'}
      >
        {stateAttribution ? `Natural Earth · ADM1: ${stateAttribution}` : 'Natural Earth · geoBoundaries ADM1 on selection'}
      </div>
    </div>
  )
}

export function NakshaInteractiveGlobe() {
  return (
    <GlobeVisualBoundary>
      <NakshaInteractiveGlobeInner />
    </GlobeVisualBoundary>
  )
}
