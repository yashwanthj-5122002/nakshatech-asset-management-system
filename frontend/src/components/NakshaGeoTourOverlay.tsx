import { useEffect, useMemo, useRef, useState } from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import { feature as topojsonFeature } from 'topojson-client'
import worldAtlas from 'world-atlas/countries-110m.json'
import '../login-geo-tour.css'

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

type BoundaryLayer = 'country' | 'state' | 'district'

type TourPolygon = BaseGeoFeature & {
  __layer: BoundaryLayer
  displayName: string
}

type GeoFeatureCollection = {
  type: 'FeatureCollection'
  features: BaseGeoFeature[]
  title?: string
  version?: string
  copyright?: string
  copyrightShort?: string
  copyrightUrl?: string
}

type GeoBoundaryMetadata = {
  boundarySource?: string
  boundaryLicense?: string
  simplifiedGeometryGeoJSON?: string
}

type TourStage = 'world' | 'india' | 'karnataka' | 'bengaluru'

type TourPoint = {
  name: string
  lat: number
  lng: number
}

type BoundaryResult = {
  features: TourPolygon[]
  attribution: string
}

const INDIA_NUMERIC_ID = '356'
const WORLD_POV = { lat: 18, lng: 58, altitude: 1.58 }
const INDIA_POV = { lat: 21.0, lng: 78.7, altitude: 0.72 }
const KARNATAKA_POV = { lat: 15.25, lng: 76.3, altitude: 0.34 }
const BENGALURU_POV = { lat: 12.9716, lng: 77.5946, altitude: 0.20 }
const BENGALURU_POINT: TourPoint = { name: 'Bengaluru', lat: 12.9716, lng: 77.5946 }

const HIGHCHARTS_MAP_REVISION = 'd668c517b7f8bde69be83b5bad6a41a88a072843'
const INDIA_MAPS_REVISION = '2884453'

// IMPORTANT: This must be an ADM1/state collection, never the India-wide district file.
const INDIA_STATE_GEOJSON_SOURCES = [
  `https://cdn.jsdelivr.net/gh/highcharts/map-collection-dist@${HIGHCHARTS_MAP_REVISION}/countries/in/in-all.geo.json`,
  'https://code.highcharts.com/mapdata/2.3.3/countries/in/in-all.geo.json',
]

const KARNATAKA_DISTRICT_GEOJSON_SOURCES = [
  `https://cdn.jsdelivr.net/gh/udit-001/india-maps-data@${INDIA_MAPS_REVISION}/geojson/states/karnataka.geojson`,
]

function normalizeName(value: string) {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function isPolygonGeometry(geometry: BaseGeoFeature['geometry'] | undefined): geometry is PolygonGeometry {
  return geometry?.type === 'Polygon' || geometry?.type === 'MultiPolygon'
}

function isCoordinate(value: unknown): value is [number, number] {
  return Array.isArray(value) && value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number'
}

function collectCoordinates(value: unknown, output: Array<[number, number]>) {
  if (isCoordinate(value)) {
    output.push([value[0], value[1]])
    return
  }
  if (!Array.isArray(value)) return
  for (const child of value) collectCoordinates(child, output)
}

function ringContainsPoint(ring: unknown, point: [number, number]) {
  if (!Array.isArray(ring)) return false
  const points = ring.filter(isCoordinate)
  if (points.length < 3) return false

  const [x, y] = point
  let inside = false
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i]
    const [xj, yj] = points[j]
    const crosses = ((yi > y) !== (yj > y)) &&
      x < ((xj - xi) * (y - yi)) / ((yj - yi) || Number.EPSILON) + xi
    if (crosses) inside = !inside
  }
  return inside
}

function polygonCoordinatesContainPoint(polygon: unknown, point: [number, number]) {
  if (!Array.isArray(polygon) || !polygon.length) return false
  if (!ringContainsPoint(polygon[0], point)) return false
  for (let index = 1; index < polygon.length; index += 1) {
    if (ringContainsPoint(polygon[index], point)) return false
  }
  return true
}

function geometryContainsPoint(geometry: PolygonGeometry, point: [number, number]) {
  if (geometry.type === 'Polygon') {
    return polygonCoordinatesContainPoint(geometry.coordinates, point)
  }
  if (!Array.isArray(geometry.coordinates)) return false
  return geometry.coordinates.some((polygon) => polygonCoordinatesContainPoint(polygon, point))
}

function representativePoints(feature: BaseGeoFeature): Array<[number, number]> {
  const coordinates: Array<[number, number]> = []
  collectCoordinates(feature.geometry.coordinates, coordinates)
  if (!coordinates.length) return []

  let sumLng = 0
  let sumLat = 0
  let minLng = Number.POSITIVE_INFINITY
  let minLat = Number.POSITIVE_INFINITY
  let maxLng = Number.NEGATIVE_INFINITY
  let maxLat = Number.NEGATIVE_INFINITY

  for (const [lng, lat] of coordinates) {
    sumLng += lng
    sumLat += lat
    minLng = Math.min(minLng, lng)
    minLat = Math.min(minLat, lat)
    maxLng = Math.max(maxLng, lng)
    maxLat = Math.max(maxLat, lat)
  }

  return [
    [sumLng / coordinates.length, sumLat / coordinates.length],
    [(minLng + maxLng) / 2, (minLat + maxLat) / 2],
  ]
}

function childBelongsToParent(child: BaseGeoFeature, parent: BaseGeoFeature) {
  return representativePoints(child).some((point) => geometryContainsPoint(parent.geometry, point))
}

function firstProperty(feature: BaseGeoFeature, keys: string[]) {
  const properties = feature.properties ?? {}
  for (const key of keys) {
    const value = properties[key]
    if (value !== undefined && value !== null && String(value).trim()) return String(value)
  }
  return ''
}

function featureDisplayName(feature: BaseGeoFeature, layer: Exclude<BoundaryLayer, 'country'>, index: number) {
  const stateKeys = ['shapeName', 'st_nm', 'ST_NM', 'state', 'State', 'STATE', 'NAME_1', 'name', 'Name', 'NAME']
  const districtKeys = ['shapeName', 'district', 'District', 'DISTRICT', 'dtname', 'DTNAME', 'NAME_2', 'name', 'Name', 'NAME']
  const keys = layer === 'state' ? stateKeys : districtKeys
  return firstProperty(feature, keys) || `${layer} ${index + 1}`
}

function normalizeBoundaryCollection(
  collection: GeoFeatureCollection,
  layer: Exclude<BoundaryLayer, 'country'>,
  idPrefix: string,
) {
  return collection.features
    .filter((feature) => isPolygonGeometry(feature.geometry))
    .map((feature, index) => ({
      ...feature,
      id: feature.id ?? `${idPrefix}-${index}`,
      __layer: layer,
      displayName: featureDisplayName(feature, layer, index),
    } satisfies TourPolygon))
}

function isIndiaCountry(feature: TourPolygon) {
  return String(feature.id ?? '').padStart(3, '0') === INDIA_NUMERIC_ID
}

function isKarnataka(feature: TourPolygon) {
  return normalizeName(feature.displayName) === 'karnataka'
}

function isBengaluruUrban(feature: TourPolygon) {
  const name = normalizeName(feature.displayName)
  return name === 'bengaluru urban' || name === 'bangalore urban' || name === 'bengaluru' || name === 'bangalore'
}

function isValidIndiaStateCollection(features: TourPolygon[]) {
  if (features.length < 28 || features.length > 50 || !features.some(isKarnataka)) return false
  const admin1Rows = features.filter(
    (feature) => normalizeName(firstProperty(feature, ['hc-group', 'admin_level', 'shapeType'])) === 'admin1',
  )
  return admin1Rows.length === 0 || admin1Rows.length >= Math.floor(features.length * 0.8)
}

function isValidKarnatakaDistrictCollection(features: TourPolygon[]) {
  if (features.length < 20 || features.length > 50 || !features.some(isBengaluruUrban)) return false
  const karnatakaRows = features.filter(
    (feature) => normalizeName(firstProperty(feature, ['st_nm', 'ST_NM', 'state', 'State', 'STATE'])) === 'karnataka',
  )
  return karnatakaRows.length === 0 || karnatakaRows.length >= Math.floor(features.length * 0.8)
}

async function fetchJson<T>(url: string, timeoutMs = 12000): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: 'application/json, application/geo+json;q=0.9, */*;q=0.8' },
      cache: 'force-cache',
    })
    if (!response.ok) throw new Error(`Boundary request failed (${response.status})`)
    return await response.json() as T
  } finally {
    window.clearTimeout(timeout)
  }
}

async function fetchJsonWithFallback<T>(urls: string[], timeoutMs = 12000): Promise<T> {
  let lastError: unknown = new Error('Boundary source unavailable')
  for (const url of urls) {
    try {
      return await fetchJson<T>(url, timeoutMs)
    } catch (error) {
      lastError = error
    }
  }
  throw lastError
}

async function loadIndiaBoundary(
  admLevel: 'ADM1' | 'ADM2',
  layer: Exclude<BoundaryLayer, 'country'>,
): Promise<BoundaryResult> {
  const metadata = await fetchJson<GeoBoundaryMetadata>(
    `https://www.geoboundaries.org/api/current/gbOpen/IND/${admLevel}/`,
  )
  if (!metadata.simplifiedGeometryGeoJSON) throw new Error(`${admLevel} geometry unavailable`)

  const collection = await fetchJson<GeoFeatureCollection>(metadata.simplifiedGeometryGeoJSON, 16000)
  return {
    features: normalizeBoundaryCollection(collection, layer, `IND-${admLevel}`),
    attribution: [metadata.boundarySource, metadata.boundaryLicense].filter(Boolean).join(' · '),
  }
}

async function loadIndiaStates(): Promise<BoundaryResult> {
  try {
    const collection = await fetchJsonWithFallback<GeoFeatureCollection>(INDIA_STATE_GEOJSON_SOURCES, 12000)
    const features = normalizeBoundaryCollection(collection, 'state', 'IND-STATE')
    if (isValidIndiaStateCollection(features)) {
      return {
        features,
        attribution: 'Highcharts Map Collection · Highsoft AS · OpenStreetMap',
      }
    }
  } catch {
    // Use the ADM1 fallback below.
  }

  const fallback = await loadIndiaBoundary('ADM1', 'state')
  if (!isValidIndiaStateCollection(fallback.features)) {
    throw new Error('India ADM1 boundary source returned the wrong granularity')
  }
  return fallback
}

async function loadKarnatakaDistricts(): Promise<BoundaryResult> {
  try {
    const collection = await fetchJsonWithFallback<GeoFeatureCollection>(KARNATAKA_DISTRICT_GEOJSON_SOURCES, 12000)
    const features = normalizeBoundaryCollection(collection, 'district', 'KA-DISTRICT')
    if (isValidKarnatakaDistrictCollection(features)) {
      return {
        features,
        attribution: 'India Maps Data · Karnataka district boundaries',
      }
    }
  } catch {
    // Use the ADM2 fallback below.
  }

  const [stateResult, districtResult] = await Promise.all([
    loadIndiaBoundary('ADM1', 'state'),
    loadIndiaBoundary('ADM2', 'district'),
  ])
  const state = stateResult.features.find(isKarnataka)
  if (!state) throw new Error('Karnataka state boundary unavailable')

  const features = districtResult.features.filter((feature) => childBelongsToParent(feature, state))
  if (!isValidKarnatakaDistrictCollection(features)) {
    throw new Error('Karnataka ADM2 boundary source returned the wrong granularity')
  }
  return { features, attribution: districtResult.attribution }
}

function sleep(duration: number, cancelled: () => boolean) {
  return new Promise<void>((resolve) => {
    const started = performance.now()
    const tick = () => {
      if (cancelled() || performance.now() - started >= duration) {
        resolve()
        return
      }
      window.setTimeout(tick, Math.min(120, duration))
    }
    tick()
  })
}

function layerLabel(stage: TourStage) {
  if (stage === 'india') return 'INDIA · STATE BOUNDARIES'
  if (stage === 'karnataka') return 'KARNATAKA · DISTRICT BOUNDARIES'
  if (stage === 'bengaluru') return 'BENGALURU URBAN · KARNATAKA'
  return 'NAKSHA GIS · GLOBAL VIEW'
}

function layerDescription(stage: TourStage, stateCount: number, districtCount: number) {
  if (stage === 'india') {
    return stateCount
      ? `India located · ${stateCount} state / union territory boundaries loaded`
      : 'India located · loading state / union territory boundaries'
  }
  if (stage === 'karnataka') {
    return districtCount
      ? `Karnataka isolated · ${districtCount} district boundaries loaded`
      : 'Karnataka isolated · loading district boundaries'
  }
  if (stage === 'bengaluru') {
    return districtCount
      ? `Bengaluru Urban highlighted · ${districtCount} Karnataka districts visible`
      : 'Bengaluru focus · Karnataka district boundaries unavailable'
  }
  return 'Rotating world view · beginning geographic fly-in'
}

export function NakshaGeoTourOverlay({ onComplete }: { onComplete: () => void }) {
  const globeRef = useRef<GlobeMethods>()
  const hostRef = useRef<HTMLDivElement | null>(null)
  const onCompleteRef = useRef(onComplete)
  const [dimensions, setDimensions] = useState({ width: 1280, height: 760 })
  const [ready, setReady] = useState(false)
  const [stage, setStage] = useState<TourStage>('world')
  const [states, setStates] = useState<TourPolygon[]>([])
  const [districts, setDistricts] = useState<TourPolygon[]>([])
  const [attribution, setAttribution] = useState('')
  const [fading, setFading] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [compact, setCompact] = useState(false)

  useEffect(() => { onCompleteRef.current = onComplete }, [onComplete])

  const countries = useMemo<TourPolygon[]>(() => {
    const topology = worldAtlas as unknown as { objects: { countries: unknown } }
    const collection = topojsonFeature(
      worldAtlas as never,
      topology.objects.countries as never,
    ) as unknown as GeoFeatureCollection

    return collection.features
      .filter((feature) => isPolygonGeometry(feature.geometry))
      .map((feature) => ({
        ...feature,
        __layer: 'country' as const,
        displayName: String(feature.properties?.name ?? 'Country'),
      }))
  }, [])

  const indiaCountry = useMemo(
    () => countries.find(isIndiaCountry) ?? null,
    [countries],
  )
  const karnatakaState = useMemo(
    () => states.find(isKarnataka) ?? null,
    [states],
  )

  const polygons = useMemo(() => {
    if (stage === 'world') return countries
    if (stage === 'india') {
      return indiaCountry ? [indiaCountry, ...states] : states
    }
    if (districts.length) return districts
    return karnatakaState ? [karnatakaState] : []
  }, [countries, districts, indiaCountry, karnatakaState, stage, states])

  useEffect(() => {
    const host = hostRef.current
    if (!host || typeof window === 'undefined') return

    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const updatePreferences = () => setReducedMotion(motionQuery.matches)
    updatePreferences()

    const resize = () => {
      const rect = host.getBoundingClientRect()
      setDimensions({
        width: Math.max(320, Math.round(rect.width)),
        height: Math.max(320, Math.round(rect.height)),
      })
      setCompact(rect.width < 780)
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(host)
    motionQuery.addEventListener?.('change', updatePreferences)

    return () => {
      observer.disconnect()
      motionQuery.removeEventListener?.('change', updatePreferences)
    }
  }, [])

  useEffect(() => {
    if (!ready) return
    let cancelled = false
    const isCancelled = () => cancelled

    const runTour = async () => {
      const globe = globeRef.current
      const controls = globe?.controls()
      if (!globe || !controls) {
        onCompleteRef.current()
        return
      }

      const stateRequest = loadIndiaStates()
      const districtRequest = loadKarnatakaDistricts()

      controls.enablePan = false
      controls.enableZoom = false
      controls.enableRotate = false
      controls.autoRotate = !reducedMotion
      controls.autoRotateSpeed = 0.38
      globe.pointOfView(WORLD_POV, reducedMotion ? 0 : 500)

      await sleep(reducedMotion ? 350 : 2200, isCancelled)
      if (cancelled) return

      controls.autoRotate = false
      setStage('india')
      globe.pointOfView(INDIA_POV, reducedMotion ? 0 : 1450)

      try {
        const result = await stateRequest
        if (cancelled) return
        setStates(result.features)
        setAttribution(result.attribution)
      } catch {
        setStates([])
      }

      await sleep(reducedMotion ? 300 : 1900, isCancelled)
      if (cancelled) return

      setStage('karnataka')
      globe.pointOfView(KARNATAKA_POV, reducedMotion ? 0 : 1450)

      let districtRows: TourPolygon[] = []
      try {
        const result = await districtRequest
        if (cancelled) return
        districtRows = result.features
        setDistricts(districtRows)
        setAttribution((current) => current || result.attribution)
      } catch {
        setDistricts([])
      }

      await sleep(reducedMotion ? 350 : districtRows.length ? 2300 : 1600, isCancelled)
      if (cancelled) return

      setStage('bengaluru')
      globe.pointOfView(BENGALURU_POV, reducedMotion ? 0 : 1550)
      await sleep(reducedMotion ? 600 : 3000, isCancelled)
      if (cancelled) return

      setFading(true)
      await sleep(reducedMotion ? 80 : 720, isCancelled)
      if (!cancelled) onCompleteRef.current()
    }

    void runTour()
    return () => { cancelled = true }
  }, [ready, reducedMotion])

  const polygonCapColor = (polygon: TourPolygon) => {
    if (polygon.__layer === 'country') {
      if (isIndiaCountry(polygon) && stage === 'india') return 'rgba(5, 65, 94, .10)'
      return 'rgba(5, 36, 62, .74)'
    }
    if (polygon.__layer === 'state') {
      if (isKarnataka(polygon) && stage !== 'india') return 'rgba(9, 153, 185, .28)'
      return 'rgba(5, 54, 78, .08)'
    }
    if (stage === 'bengaluru' && isBengaluruUrban(polygon)) return 'rgba(51, 224, 239, .54)'
    return 'rgba(6, 96, 126, .10)'
  }

  const polygonStrokeColor = (polygon: TourPolygon) => {
    if (polygon.__layer === 'country') {
      if (isIndiaCountry(polygon) && stage === 'india') return '#5ee9f5'
      return 'rgba(57, 156, 207, .42)'
    }
    if (polygon.__layer === 'state') {
      if (isKarnataka(polygon) && stage !== 'india') return '#c4fbff'
      return 'rgba(116, 232, 244, .98)'
    }
    if (stage === 'bengaluru' && isBengaluruUrban(polygon)) return '#ffffff'
    return 'rgba(202, 249, 253, .94)'
  }

  const polygonAltitude = (polygon: TourPolygon) => {
    if (polygon.__layer === 'state') {
      return isKarnataka(polygon) && stage !== 'india' ? 0.018 : 0.014
    }
    if (polygon.__layer === 'district') {
      return stage === 'bengaluru' && isBengaluruUrban(polygon) ? 0.030 : 0.022
    }
    return isIndiaCountry(polygon) && stage === 'india' ? 0.003 : 0.002
  }

  const points = stage === 'bengaluru' ? [BENGALURU_POINT] : []

  return (
    <div ref={hostRef} className={`naksha-geo-tour ${fading ? 'is-fading' : ''}`} aria-hidden="true">
      <div className="naksha-geo-tour-stage">
        <Globe
          ref={globeRef}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="rgba(0,0,0,0)"
          showAtmosphere
          atmosphereColor="#16c7e8"
          atmosphereAltitude={0.13}
          rendererConfig={{ antialias: !compact, alpha: true }}
          animateIn={!reducedMotion}
          polygonsData={polygons}
          polygonCapColor={(polygon: unknown) => polygonCapColor(polygon as TourPolygon)}
          polygonSideColor={() => 'rgba(2, 21, 38, .24)'}
          polygonStrokeColor={(polygon: unknown) => polygonStrokeColor(polygon as TourPolygon)}
          polygonAltitude={(polygon: unknown) => polygonAltitude(polygon as TourPolygon)}
          polygonCapCurvatureResolution={compact ? 8 : 4}
          polygonsTransitionDuration={reducedMotion ? 0 : 360}
          pointsData={points}
          pointLat="lat"
          pointLng="lng"
          pointColor={() => '#f2ffff'}
          pointAltitude={0.038}
          pointRadius={0.30}
          pointResolution={10}
          labelsData={points}
          labelLat="lat"
          labelLng="lng"
          labelText="name"
          labelColor={() => 'rgba(232,253,255,.98)'}
          labelAltitude={0.052}
          labelSize={0.48}
          labelDotRadius={0.075}
          labelResolution={2}
          onGlobeReady={() => setReady(true)}
          enablePointerInteraction={false}
          showPointerCursor={false}
        />
      </div>

      <div className="naksha-geo-tour-status">
        <span className="naksha-geo-tour-pulse" />
        <div>
          <strong>{layerLabel(stage)}</strong>
          <small>{layerDescription(stage, states.length, districts.length)}</small>
        </div>
      </div>

      <div className="naksha-geo-tour-path">
        <span className={stage === 'world' ? 'active' : 'done'}>World</span>
        <i />
        <span className={stage === 'india' ? 'active' : stage === 'world' ? '' : 'done'}>India</span>
        <i />
        <span className={stage === 'karnataka' ? 'active' : stage === 'bengaluru' ? 'done' : ''}>Karnataka</span>
        <i />
        <span className={stage === 'bengaluru' ? 'active' : ''}>Bengaluru</span>
      </div>

      <div className="naksha-geo-tour-source">
        {attribution ? `Administrative boundaries: ${attribution}` : 'Administrative boundaries loading'}
      </div>
    </div>
  )
}
