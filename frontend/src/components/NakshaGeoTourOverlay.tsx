import { useEffect, useMemo, useRef, useState } from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import { feature as topojsonFeature, merge as topojsonMerge } from 'topojson-client'
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

type DistrictTopologyGeometry = {
  type: 'Polygon' | 'MultiPolygon'
  arcs: unknown
  properties?: Record<string, unknown>
}

type IndiaDistrictTopology = {
  type: 'Topology'
  objects: {
    districts: {
      type: 'GeometryCollection'
      geometries: DistrictTopologyGeometry[]
    }
  }
  arcs: unknown
  transform?: unknown
  bbox?: unknown
}

type IndiaMapData = {
  indiaBoundary: TourPolygon
  states: TourPolygon[]
  karnatakaState: TourPolygon
  karnatakaDistricts: TourPolygon[]
  attribution: string
}

type TourStage = 'world' | 'india' | 'karnataka' | 'bengaluru'

type TourPoint = {
  name: string
  lat: number
  lng: number
}

const WORLD_POV = { lat: 18, lng: 58, altitude: 1.58 }
const INDIA_POV = { lat: 21.0, lng: 78.7, altitude: 0.88 }
const KARNATAKA_POV = { lat: 15.25, lng: 75.9, altitude: 0.58 }
const BENGALURU_POV = { lat: 12.9716, lng: 77.5946, altitude: 0.44 }
const BENGALURU_POINT: TourPoint = { name: 'Bengaluru', lat: 12.9716, lng: 77.5946 }

const INDIA_MAPS_REVISION = '2884453'
const INDIA_TOPOLOGY_SOURCES = [
  `https://cdn.jsdelivr.net/gh/udit-001/india-maps-data@${INDIA_MAPS_REVISION}/topojson/india.json`,
  `https://raw.githubusercontent.com/udit-001/india-maps-data/${INDIA_MAPS_REVISION}/topojson/india.json`,
]

let indiaMapDataRequest: Promise<IndiaMapData> | null = null

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

function stateNameFromProperties(properties?: Record<string, unknown>) {
  const value = properties?.st_nm ?? properties?.state ?? properties?.State ?? properties?.STATE
  return value === undefined || value === null ? '' : String(value).trim()
}

function districtNameFromProperties(properties?: Record<string, unknown>) {
  const value = properties?.district ?? properties?.District ?? properties?.DISTRICT ?? properties?.name
  return value === undefined || value === null ? '' : String(value).trim()
}

function isKarnatakaName(value: string) {
  return normalizeName(value) === 'karnataka'
}

function isBengaluruUrbanName(value: string) {
  const name = normalizeName(value)
  return name === 'bengaluru urban' || name === 'bangalore urban' || name === 'bengaluru' || name === 'bangalore'
}

function isKarnataka(feature: TourPolygon) {
  return isKarnatakaName(feature.displayName)
}

function isBengaluruUrban(feature: TourPolygon) {
  return isBengaluruUrbanName(feature.displayName)
}

async function fetchJson<T>(url: string, timeoutMs = 16000): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { Accept: 'application/json, application/topo+json;q=0.9, */*;q=0.8' },
      cache: 'force-cache',
    })
    if (!response.ok) throw new Error(`Boundary request failed (${response.status})`)
    return await response.json() as T
  } finally {
    window.clearTimeout(timeout)
  }
}

async function fetchIndiaTopology() {
  let lastError: unknown = new Error('India topology unavailable')
  for (const url of INDIA_TOPOLOGY_SOURCES) {
    try {
      const topology = await fetchJson<IndiaDistrictTopology>(url)
      if (
        topology?.type === 'Topology' &&
        topology.objects?.districts?.type === 'GeometryCollection' &&
        Array.isArray(topology.objects.districts.geometries) &&
        topology.objects.districts.geometries.length > 500
      ) {
        return topology
      }
      lastError = new Error('India topology has an unexpected structure')
    } catch (error) {
      lastError = error
    }
  }
  throw lastError
}

function buildIndiaMapData(topology: IndiaDistrictTopology): IndiaMapData {
  const districtObject = topology.objects.districts
  const districtCollection = topojsonFeature(
    topology as never,
    districtObject as never,
  ) as unknown as GeoFeatureCollection

  const districtFeatures = districtCollection.features.filter(
    (feature) => isPolygonGeometry(feature.geometry),
  )

  const stateGeometryGroups = new Map<string, DistrictTopologyGeometry[]>()
  for (const geometry of districtObject.geometries) {
    const stateName = stateNameFromProperties(geometry.properties)
    if (!stateName) continue
    const key = normalizeName(stateName)
    const group = stateGeometryGroups.get(key) ?? []
    group.push(geometry)
    stateGeometryGroups.set(key, group)
  }

  const states: TourPolygon[] = []
  for (const [stateKey, geometries] of stateGeometryGroups.entries()) {
    if (!geometries.length) continue
    const stateName = stateNameFromProperties(geometries[0].properties)
    const merged = topojsonMerge(
      topology as never,
      geometries as never,
    ) as unknown
    if (!isPolygonGeometry(merged)) continue

    states.push({
      type: 'Feature',
      id: `IND-STATE-${stateKey}`,
      properties: {
        name: stateName,
        st_nm: stateName,
        st_code: geometries[0].properties?.st_code,
      },
      geometry: merged,
      __layer: 'state',
      displayName: stateName,
    })
  }

  states.sort((a, b) => a.displayName.localeCompare(b.displayName))

  if (states.length < 28 || states.length > 50 || !states.some(isKarnataka)) {
    throw new Error(`Unexpected India state topology (${states.length} state geometries)`)
  }

  const allDistrictGeometries = districtObject.geometries.filter(
    (geometry) => stateNameFromProperties(geometry.properties),
  )
  const indiaMerged = topojsonMerge(
    topology as never,
    allDistrictGeometries as never,
  ) as unknown
  if (!isPolygonGeometry(indiaMerged)) {
    throw new Error('Unable to derive India boundary from district topology')
  }

  const indiaBoundary: TourPolygon = {
    type: 'Feature',
    id: 'INDIA-BOUNDARY',
    properties: { name: 'India' },
    geometry: indiaMerged,
    __layer: 'country',
    displayName: 'India',
  }

  const karnatakaState = states.find(isKarnataka)
  if (!karnatakaState) throw new Error('Karnataka state geometry unavailable')

  const karnatakaDistricts: TourPolygon[] = districtFeatures
    .filter((feature) => isKarnatakaName(stateNameFromProperties(feature.properties)))
    .map((feature, index) => ({
      ...feature,
      id: feature.id ?? `KA-DISTRICT-${index}`,
      __layer: 'district' as const,
      displayName: districtNameFromProperties(feature.properties) || `District ${index + 1}`,
    }))
    .sort((a, b) => a.displayName.localeCompare(b.displayName))

  if (
    karnatakaDistricts.length < 20 ||
    karnatakaDistricts.length > 50 ||
    !karnatakaDistricts.some(isBengaluruUrban)
  ) {
    throw new Error(`Unexpected Karnataka district topology (${karnatakaDistricts.length} districts)`)
  }

  return {
    indiaBoundary,
    states,
    karnatakaState,
    karnatakaDistricts,
    attribution: 'India Maps Data · WGS84 TopoJSON · district/state geometry derived from one topology',
  }
}

function getIndiaMapData() {
  if (!indiaMapDataRequest) {
    indiaMapDataRequest = fetchIndiaTopology()
      .then(buildIndiaMapData)
      .catch((error) => {
        indiaMapDataRequest = null
        throw error
      })
  }
  return indiaMapDataRequest
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

function layerDescription(stage: TourStage, data: IndiaMapData | null, boundaryError: boolean) {
  if (boundaryError) return 'Administrative boundary data unavailable · continuing with the secure login globe'
  if (stage === 'india') {
    return data
      ? `India located · ${data.states.length} state / union territory boundaries visible`
      : 'India located · loading state / union territory boundaries'
  }
  if (stage === 'karnataka') {
    return data
      ? `Karnataka highlighted · ${data.karnatakaDistricts.length} district boundaries visible`
      : 'Karnataka highlighted · loading district boundaries'
  }
  if (stage === 'bengaluru') {
    return data
      ? 'Bengaluru Urban highlighted · Karnataka district context retained'
      : 'Bengaluru focus · loading Karnataka district context'
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
  const [indiaData, setIndiaData] = useState<IndiaMapData | null>(null)
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
    if (stage === 'world') return countries
    if (!indiaData) return []
    if (stage === 'india') return [indiaData.indiaBoundary, ...indiaData.states]
    return [indiaData.karnatakaState, ...indiaData.karnatakaDistricts]
  }, [countries, indiaData, stage])

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

      const mapRequest = getIndiaMapData()

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

      let data: IndiaMapData | null = null
      try {
        data = await mapRequest
        if (cancelled) return
        setIndiaData(data)
        setBoundaryError(false)
      } catch {
        if (cancelled) return
        setBoundaryError(true)
      }

      await sleep(reducedMotion ? 300 : data ? 2100 : 900, isCancelled)
      if (cancelled) return

      if (!data) {
        setFading(true)
        await sleep(reducedMotion ? 80 : 600, isCancelled)
        if (!cancelled) onCompleteRef.current()
        return
      }

      setStage('karnataka')
      globe.pointOfView(KARNATAKA_POV, reducedMotion ? 0 : 1450)
      await sleep(reducedMotion ? 350 : 2300, isCancelled)
      if (cancelled) return

      setStage('bengaluru')
      globe.pointOfView(BENGALURU_POV, reducedMotion ? 0 : 1500)
      await sleep(reducedMotion ? 600 : 2800, isCancelled)
      if (cancelled) return

      setFading(true)
      await sleep(reducedMotion ? 80 : 720, isCancelled)
      if (!cancelled) onCompleteRef.current()
    }

    void runTour()
    return () => { cancelled = true }
  }, [ready, reducedMotion])

  const polygonCapColor = (polygon: TourPolygon) => {
    if (stage === 'world') return 'rgba(5, 36, 62, .74)'

    if (polygon.__layer === 'country') {
      return 'rgba(5, 65, 94, .08)'
    }

    if (polygon.__layer === 'state') {
      return stage === 'india'
        ? 'rgba(5, 54, 78, .08)'
        : 'rgba(9, 153, 185, .14)'
    }

    if (stage === 'bengaluru' && isBengaluruUrban(polygon)) {
      return 'rgba(51, 224, 239, .42)'
    }
    return 'rgba(6, 96, 126, .05)'
  }

  const polygonStrokeColor = (polygon: TourPolygon) => {
    if (stage === 'world') return 'rgba(57, 156, 207, .42)'

    if (polygon.__layer === 'country') return '#5ee9f5'
    if (polygon.__layer === 'state') {
      return stage === 'india' ? 'rgba(116, 232, 244, .94)' : '#bdf8ff'
    }
    if (stage === 'bengaluru' && isBengaluruUrban(polygon)) return '#ffffff'
    return 'rgba(210, 250, 255, .90)'
  }

  const polygonAltitude = (polygon: TourPolygon) => {
    if (stage === 'world') return 0.002
    if (polygon.__layer === 'country') return 0.003
    if (polygon.__layer === 'state') return stage === 'india' ? 0.012 : 0.008
    return stage === 'bengaluru' && isBengaluruUrban(polygon) ? 0.021 : 0.014
  }

  const points = stage === 'bengaluru' && indiaData ? [BENGALURU_POINT] : []

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
          polygonSideColor={() => 'rgba(2, 21, 38, .20)'}
          polygonStrokeColor={(polygon: unknown) => polygonStrokeColor(polygon as TourPolygon)}
          polygonAltitude={(polygon: unknown) => polygonAltitude(polygon as TourPolygon)}
          polygonCapCurvatureResolution={compact ? 8 : 4}
          polygonsTransitionDuration={reducedMotion ? 0 : 420}
          pointsData={points}
          pointLat="lat"
          pointLng="lng"
          pointColor={() => '#f2ffff'}
          pointAltitude={0.026}
          pointRadius={0.14}
          pointResolution={10}
          labelsData={points}
          labelLat="lat"
          labelLng="lng"
          labelText="name"
          labelColor={() => 'rgba(232,253,255,.98)'}
          labelAltitude={0.034}
          labelSize={0.16}
          labelDotRadius={0.035}
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
          <small>{layerDescription(stage, indiaData, boundaryError)}</small>
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
        {indiaData ? `Administrative boundaries: ${indiaData.attribution}` : 'Administrative boundaries: loading validated India topology'}
      </div>
    </div>
  )
}
