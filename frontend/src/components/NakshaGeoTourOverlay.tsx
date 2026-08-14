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

type TourPolygon = BaseGeoFeature & {
  displayName: string
}

type GeoFeatureCollection = {
  type: 'FeatureCollection'
  features: BaseGeoFeature[]
}

type TourStage = 'world' | 'india' | 'karnataka' | 'bengaluru'
type BoundaryLayer = 'state' | 'district'
type Coordinate = [number, number]

type BoundaryPath = {
  layer: BoundaryLayer
  name: string
  points: Coordinate[]
  isKarnataka: boolean
  isBengaluruUrban: boolean
}

type BoundaryPathResult = {
  featureCount: number
  paths: BoundaryPath[]
}

type TourPoint = {
  name: string
  lat: number
  lng: number
}

const INDIA_NUMERIC_ID = '356'
const INDIA_STATES_URL = '/geo/india-states.geojson'
const KARNATAKA_DISTRICTS_URL = '/geo/karnataka-districts.geojson'

const WORLD_POV = { lat: 18, lng: 58, altitude: 1.58 }
const INDIA_POV = { lat: 21.0, lng: 78.7, altitude: 0.88 }
const KARNATAKA_POV = { lat: 15.25, lng: 75.7, altitude: 0.57 }
const BENGALURU_POV = { lat: 12.9716, lng: 77.5946, altitude: 0.42 }
const BENGALURU_POINT: TourPoint = { name: 'Bengaluru', lat: 12.9716, lng: 77.5946 }

// Display-only thinning. Source GeoJSON remains unchanged and authoritative.
const STATE_DISPLAY_STEP = 0.01
const DISTRICT_DISPLAY_STEP = 0.005

let stateBoundaryRequest: Promise<BoundaryPathResult> | null = null
let districtBoundaryRequest: Promise<BoundaryPathResult> | null = null

function normalizeName(value: string) {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}

function isPolygonGeometry(geometry: unknown): geometry is PolygonGeometry {
  if (!geometry || typeof geometry !== 'object') return false
  const type = (geometry as { type?: unknown }).type
  return type === 'Polygon' || type === 'MultiPolygon'
}

function propertyText(feature: BaseGeoFeature, keys: string[]) {
  const properties = feature.properties ?? {}
  for (const key of keys) {
    const value = properties[key]
    if (value !== undefined && value !== null && String(value).trim()) {
      return String(value).trim()
    }
  }
  return ''
}

function isIndiaCountry(feature: TourPolygon) {
  return String(feature.id ?? '').padStart(3, '0') === INDIA_NUMERIC_ID || normalizeName(feature.displayName) === 'india'
}

function isKarnatakaName(value: string) {
  return normalizeName(value) === 'karnataka'
}

function isBengaluruUrbanName(value: string) {
  const name = normalizeName(value)
  return name === 'bengaluru urban' || name === 'bangalore urban' || name === 'bengaluru' || name === 'bangalore'
}

function isCoordinate(value: unknown): value is Coordinate {
  return Array.isArray(value)
    && value.length >= 2
    && Number.isFinite(Number(value[0]))
    && Number.isFinite(Number(value[1]))
}

function thinRing(rawRing: unknown, minimumStep: number): Coordinate[] {
  if (!Array.isArray(rawRing)) return []

  const points = rawRing
    .filter(isCoordinate)
    .map((point) => [Number(point[0]), Number(point[1])] as Coordinate)

  if (points.length <= 4) return points

  const minimumDistanceSquared = minimumStep * minimumStep
  const reduced: Coordinate[] = [points[0]]
  let lastKept = points[0]

  for (let index = 1; index < points.length - 1; index += 1) {
    const point = points[index]
    const dx = point[0] - lastKept[0]
    const dy = point[1] - lastKept[1]
    if ((dx * dx) + (dy * dy) >= minimumDistanceSquared) {
      reduced.push(point)
      lastKept = point
    }
  }

  reduced.push(points[points.length - 1])
  return reduced.length >= 4 ? reduced : points
}

function geometryRings(geometry: PolygonGeometry) {
  if (geometry.type === 'Polygon') {
    return Array.isArray(geometry.coordinates) ? geometry.coordinates as unknown[] : []
  }

  if (!Array.isArray(geometry.coordinates)) return []
  const rings: unknown[] = []
  for (const polygon of geometry.coordinates as unknown[]) {
    if (!Array.isArray(polygon)) continue
    rings.push(...polygon)
  }
  return rings
}

async function fetchGeoJson(url: string): Promise<GeoFeatureCollection> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 20000)
  try {
    const response = await fetch(`${url}?v=20260814-2`, {
      signal: controller.signal,
      headers: { Accept: 'application/geo+json, application/json;q=0.9, */*;q=0.8' },
      cache: 'no-store',
    })
    if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`)

    const contentType = response.headers.get('content-type') ?? ''
    if (contentType.includes('text/html')) {
      throw new Error(`${url} returned HTML instead of GeoJSON`)
    }

    const data = await response.json() as GeoFeatureCollection
    if (data.type !== 'FeatureCollection' || !Array.isArray(data.features)) {
      throw new Error(`${url} is not a GeoJSON FeatureCollection`)
    }
    return data
  } finally {
    window.clearTimeout(timeout)
  }
}

function toBoundaryPaths(collection: GeoFeatureCollection, layer: BoundaryLayer): BoundaryPathResult {
  const nameKeys = layer === 'state'
    ? ['st_nm', 'state', 'State', 'STATE', 'name', 'NAME']
    : ['dtname', 'district', 'District', 'DISTRICT', 'name', 'NAME']
  const minimumStep = layer === 'state' ? STATE_DISPLAY_STEP : DISTRICT_DISPLAY_STEP

  const polygonFeatures = collection.features.filter((feature) => isPolygonGeometry(feature.geometry))
  const paths: BoundaryPath[] = []

  for (const feature of polygonFeatures) {
    const name = propertyText(feature, nameKeys)
    if (!name) continue

    for (const ring of geometryRings(feature.geometry)) {
      const points = thinRing(ring, minimumStep)
      if (points.length < 4) continue
      paths.push({
        layer,
        name,
        points,
        isKarnataka: isKarnatakaName(name),
        isBengaluruUrban: isBengaluruUrbanName(name),
      })
    }
  }

  const featureNames = new Set(paths.map((path) => normalizeName(path.name)))
  if (layer === 'state') {
    if (featureNames.size < 28 || featureNames.size > 50 || !featureNames.has('karnataka')) {
      throw new Error(`India state file has unexpected content (${featureNames.size} named polygon features)`)
    }
  } else if (
    featureNames.size < 20
    || featureNames.size > 50
    || ![...featureNames].some((name) => name === 'bengaluru urban' || name === 'bangalore urban' || name === 'bengaluru' || name === 'bangalore')
  ) {
    throw new Error(`Karnataka district file has unexpected content (${featureNames.size} named polygon features)`)
  }

  return { featureCount: featureNames.size, paths }
}

function getStateBoundaries() {
  if (!stateBoundaryRequest) {
    stateBoundaryRequest = fetchGeoJson(INDIA_STATES_URL)
      .then((collection) => toBoundaryPaths(collection, 'state'))
      .catch((error) => {
        stateBoundaryRequest = null
        throw error
      })
  }
  return stateBoundaryRequest
}

function getDistrictBoundaries() {
  if (!districtBoundaryRequest) {
    districtBoundaryRequest = fetchGeoJson(KARNATAKA_DISTRICTS_URL)
      .then((collection) => toBoundaryPaths(collection, 'district'))
      .catch((error) => {
        districtBoundaryRequest = null
        throw error
      })
  }
  return districtBoundaryRequest
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

function layerDescription(
  stage: TourStage,
  stateCount: number,
  districtCount: number,
  boundaryError: string,
) {
  if (boundaryError) return boundaryError
  if (stage === 'india') {
    return stateCount
      ? `India located · ${stateCount} supplied state / union territory boundaries visible`
      : 'India located · loading supplied state / union territory boundaries'
  }
  if (stage === 'karnataka') {
    return districtCount
      ? `Karnataka highlighted · ${districtCount} supplied district boundaries visible`
      : 'Karnataka highlighted · loading supplied district boundaries'
  }
  if (stage === 'bengaluru') return 'Bengaluru Urban highlighted · Karnataka district context retained'
  return 'Rotating world view · beginning geographic fly-in'
}

export function NakshaGeoTourOverlay({ onComplete }: { onComplete: () => void }) {
  const globeRef = useRef<GlobeMethods>()
  const hostRef = useRef<HTMLDivElement | null>(null)
  const onCompleteRef = useRef(onComplete)
  const [dimensions, setDimensions] = useState({ width: 1280, height: 760 })
  const [ready, setReady] = useState(false)
  const [stage, setStage] = useState<TourStage>('world')
  const [statePaths, setStatePaths] = useState<BoundaryPath[]>([])
  const [districtPaths, setDistrictPaths] = useState<BoundaryPath[]>([])
  const [stateCount, setStateCount] = useState(0)
  const [districtCount, setDistrictCount] = useState(0)
  const [boundaryError, setBoundaryError] = useState('')
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
        displayName: String(feature.properties?.name ?? 'Country'),
      }))
  }, [])

  const boundaryPaths = useMemo(() => {
    if (stage === 'world') return []
    if (stage === 'india') return statePaths
    return [...statePaths, ...districtPaths]
  }, [districtPaths, stage, statePaths])

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

      const stateRequest = getStateBoundaries()

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
        const states = await stateRequest
        if (cancelled) return
        setStatePaths(states.paths)
        setStateCount(states.featureCount)
        setBoundaryError('')
      } catch (error) {
        console.warn('Naksha login India state boundaries could not be loaded.', error)
        if (cancelled) return
        setBoundaryError('India state boundary data could not be loaded')
        setFading(true)
        await sleep(reducedMotion ? 80 : 600, isCancelled)
        if (!cancelled) onCompleteRef.current()
        return
      }

      const districtRequest = getDistrictBoundaries()
      await sleep(reducedMotion ? 300 : 1900, isCancelled)
      if (cancelled) return

      setStage('karnataka')
      globe.pointOfView(KARNATAKA_POV, reducedMotion ? 0 : 1350)

      try {
        const districts = await districtRequest
        if (cancelled) return
        setDistrictPaths(districts.paths)
        setDistrictCount(districts.featureCount)
        setBoundaryError('')
      } catch (error) {
        console.warn('Naksha login Karnataka district boundaries could not be loaded.', error)
        if (cancelled) return
        setBoundaryError('Karnataka district boundary data could not be loaded')
      }

      await sleep(reducedMotion ? 350 : 2200, isCancelled)
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

  const polygonCapColor = (polygon: TourPolygon) => (
    isIndiaCountry(polygon) && stage !== 'world'
      ? 'rgba(5, 65, 94, .18)'
      : 'rgba(5, 36, 62, .74)'
  )

  const polygonStrokeColor = (polygon: TourPolygon) => (
    isIndiaCountry(polygon) && stage !== 'world'
      ? '#5ee9f5'
      : 'rgba(57, 156, 207, .42)'
  )

  const pathColor = (path: BoundaryPath) => {
    if (path.layer === 'state') {
      if (path.isKarnataka && (stage === 'karnataka' || stage === 'bengaluru')) return '#c4fbff'
      return stage === 'india' ? 'rgba(116, 232, 244, .98)' : 'rgba(100, 211, 230, .50)'
    }
    if (stage === 'bengaluru' && path.isBengaluruUrban) return '#ffffff'
    return 'rgba(202, 249, 253, .88)'
  }

  const points = stage === 'bengaluru' && districtCount ? [BENGALURU_POINT] : []

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
          polygonsData={countries}
          polygonCapColor={(polygon: unknown) => polygonCapColor(polygon as TourPolygon)}
          polygonSideColor={() => 'rgba(2, 21, 38, .24)'}
          polygonStrokeColor={(polygon: unknown) => polygonStrokeColor(polygon as TourPolygon)}
          polygonAltitude={(polygon: unknown) => isIndiaCountry(polygon as TourPolygon) && stage !== 'world' ? 0.005 : 0.002}
          polygonCapCurvatureResolution={compact ? 8 : 4}
          polygonsTransitionDuration={reducedMotion ? 0 : 360}
          pathsData={boundaryPaths}
          pathPoints="points"
          pathPointLat={(point: unknown) => (point as Coordinate)[1]}
          pathPointLng={(point: unknown) => (point as Coordinate)[0]}
          pathPointAlt={0.012}
          pathColor={(path: unknown) => pathColor(path as BoundaryPath)}
          pathStroke={0}
          pathResolution={2}
          pathTransitionDuration={reducedMotion ? 0 : 240}
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
          <small>{layerDescription(stage, stateCount, districtCount, boundaryError)}</small>
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
        {stateCount
          ? 'Administrative boundaries: NakshaTech supplied GeoJSON · display-optimized outline rendering'
          : 'Administrative boundaries: loading local NakshaTech GeoJSON'}
      </div>
    </div>
  )
}
