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
}

type TourStage = 'world' | 'india' | 'karnataka' | 'bengaluru'

type TourPoint = {
  name: string
  lat: number
  lng: number
}

type TourBoundaryData = {
  states: TourPolygon[]
  districts: TourPolygon[]
}

const INDIA_NUMERIC_ID = '356'
const INDIA_STATES_URL = '/geo/india-states.geojson'
const KARNATAKA_DISTRICTS_URL = '/geo/karnataka-districts.geojson'

// Keep the camera values from the visually approved tour.
const WORLD_POV = { lat: 18, lng: 58, altitude: 1.58 }
const INDIA_POV = { lat: 21.0, lng: 78.7, altitude: 0.88 }
const KARNATAKA_POV = { lat: 15.25, lng: 75.7, altitude: 0.57 }
const BENGALURU_POV = { lat: 12.9716, lng: 77.5946, altitude: 0.42 }
const BENGALURU_POINT: TourPoint = { name: 'Bengaluru', lat: 12.9716, lng: 77.5946 }

let boundaryDataRequest: Promise<TourBoundaryData> | null = null

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

function isKarnataka(feature: TourPolygon) {
  return normalizeName(feature.displayName) === 'karnataka'
}

function isBengaluruUrban(feature: TourPolygon) {
  const name = normalizeName(feature.displayName)
  return name === 'bengaluru urban' || name === 'bangalore urban' || name === 'bengaluru' || name === 'bangalore'
}

async function fetchGeoJson(url: string): Promise<GeoFeatureCollection> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 20000)
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: 'application/geo+json, application/json;q=0.9, */*;q=0.8' },
      cache: 'force-cache',
    })
    if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`)
    const data = await response.json() as GeoFeatureCollection
    if (data.type !== 'FeatureCollection' || !Array.isArray(data.features)) {
      throw new Error(`${url} is not a GeoJSON FeatureCollection`)
    }
    return data
  } finally {
    window.clearTimeout(timeout)
  }
}

function normalizeStates(collection: GeoFeatureCollection) {
  const states = collection.features
    .filter((feature) => isPolygonGeometry(feature.geometry))
    .map((feature, index) => ({
      ...feature,
      id: feature.id ?? `IND-STATE-${index}`,
      __layer: 'state' as const,
      displayName: propertyText(feature, ['st_nm', 'state', 'State', 'STATE', 'name', 'NAME']),
    }))
    .filter((feature) => Boolean(feature.displayName))

  if (states.length < 28 || states.length > 50 || !states.some(isKarnataka)) {
    throw new Error(`India state file has unexpected content (${states.length} polygon features)`)
  }
  return states
}

function normalizeDistricts(collection: GeoFeatureCollection) {
  const districts = collection.features
    .filter((feature) => isPolygonGeometry(feature.geometry))
    .map((feature, index) => ({
      ...feature,
      id: feature.id ?? `KA-DISTRICT-${index}`,
      __layer: 'district' as const,
      displayName: propertyText(feature, ['dtname', 'district', 'District', 'DISTRICT', 'name', 'NAME']),
    }))
    .filter((feature) => Boolean(feature.displayName))

  if (districts.length < 20 || districts.length > 50 || !districts.some(isBengaluruUrban)) {
    throw new Error(`Karnataka district file has unexpected content (${districts.length} polygon features)`)
  }
  return districts
}

function getBoundaryData() {
  if (!boundaryDataRequest) {
    boundaryDataRequest = Promise.all([
      fetchGeoJson(INDIA_STATES_URL),
      fetchGeoJson(KARNATAKA_DISTRICTS_URL),
    ])
      .then(([stateCollection, districtCollection]) => ({
        states: normalizeStates(stateCollection),
        districts: normalizeDistricts(districtCollection),
      }))
      .catch((error) => {
        boundaryDataRequest = null
        throw error
      })
  }
  return boundaryDataRequest
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

function layerDescription(stage: TourStage, data: TourBoundaryData | null, boundaryError: boolean) {
  if (boundaryError) return 'Local administrative boundary files unavailable · continuing with the secure login globe'
  if (stage === 'india') {
    return data
      ? `India located · ${data.states.length} supplied state / union territory boundaries visible`
      : 'India located · loading supplied state / union territory boundaries'
  }
  if (stage === 'karnataka') {
    return data
      ? `Karnataka highlighted · ${data.districts.length} supplied district boundaries visible`
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
  const [boundaryData, setBoundaryData] = useState<TourBoundaryData | null>(null)
  const [boundaryError, setBoundaryError] = useState(false)
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

  const polygons = useMemo(() => {
    if (stage === 'world' || !boundaryData) return countries
    if (stage === 'india') return [...countries, ...boundaryData.states]
    return [...countries, ...boundaryData.states, ...boundaryData.districts]
  }, [boundaryData, countries, stage])

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

      const dataRequest = getBoundaryData()

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

      let data: TourBoundaryData | null = null
      try {
        data = await dataRequest
        if (cancelled) return
        setBoundaryData(data)
        setBoundaryError(false)
      } catch (error) {
        console.warn('Naksha login administrative boundary files could not be loaded.', error)
        if (cancelled) return
        setBoundaryError(true)
      }

      await sleep(reducedMotion ? 300 : data ? 1900 : 900, isCancelled)
      if (cancelled) return

      if (!data) {
        setFading(true)
        await sleep(reducedMotion ? 80 : 600, isCancelled)
        if (!cancelled) onCompleteRef.current()
        return
      }

      setStage('karnataka')
      globe.pointOfView(KARNATAKA_POV, reducedMotion ? 0 : 1350)
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

  const polygonCapColor = (polygon: TourPolygon) => {
    if (polygon.__layer === 'country') {
      return isIndiaCountry(polygon) && stage !== 'world'
        ? 'rgba(5, 65, 94, .18)'
        : 'rgba(5, 36, 62, .74)'
    }

    if (polygon.__layer === 'state') {
      if (isKarnataka(polygon) && (stage === 'karnataka' || stage === 'bengaluru')) {
        return 'rgba(9, 153, 185, .34)'
      }
      return stage === 'india' ? 'rgba(5, 54, 78, .11)' : 'rgba(4, 44, 66, .07)'
    }

    if (stage === 'bengaluru' && isBengaluruUrban(polygon)) return 'rgba(51, 224, 239, .46)'
    return 'rgba(6, 96, 126, .08)'
  }

  const polygonStrokeColor = (polygon: TourPolygon) => {
    if (polygon.__layer === 'country') {
      return isIndiaCountry(polygon) && stage !== 'world'
        ? '#5ee9f5'
        : 'rgba(57, 156, 207, .42)'
    }

    if (polygon.__layer === 'state') {
      if (isKarnataka(polygon) && stage !== 'india') return '#c4fbff'
      return 'rgba(116, 232, 244, .94)'
    }

    if (stage === 'bengaluru' && isBengaluruUrban(polygon)) return '#ffffff'
    return 'rgba(202, 249, 253, .90)'
  }

  const polygonAltitude = (polygon: TourPolygon) => {
    if (polygon.__layer === 'state') {
      return isKarnataka(polygon) && stage !== 'india' ? 0.020 : 0.012
    }
    if (polygon.__layer === 'district') {
      return stage === 'bengaluru' && isBengaluruUrban(polygon) ? 0.030 : 0.024
    }
    return isIndiaCountry(polygon) && stage !== 'world' ? 0.005 : 0.002
  }

  const points = stage === 'bengaluru' && boundaryData ? [BENGALURU_POINT] : []

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
          <small>{layerDescription(stage, boundaryData, boundaryError)}</small>
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
        {boundaryData
          ? 'Administrative boundaries: NakshaTech supplied India States + Karnataka Districts GeoJSON'
          : 'Administrative boundaries: loading local NakshaTech GeoJSON'}
      </div>
    </div>
  )
}
