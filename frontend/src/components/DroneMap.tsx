import maplibregl from 'maplibre-gl'
import { useEffect, useRef } from 'react'

interface DroneMapProps {
  latitude?: number
  longitude?: number
  label?: string
}

export function DroneMap({ latitude, longitude, label = 'Drone location' }: DroneMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!containerRef.current || latitude == null || longitude == null) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      center: [longitude, latitude],
      zoom: 13,
      attributionControl: false,
      style: {
        version: 8,
        sources: {
          openstreetmap: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: 'OpenStreetMap contributors',
          },
        },
        layers: [{ id: 'openstreetmap', type: 'raster', source: 'openstreetmap' }],
      },
    })

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    new maplibregl.Marker({ color: '#12c9f5' })
      .setLngLat([longitude, latitude])
      .setPopup(new maplibregl.Popup({ offset: 18 }).setText(label))
      .addTo(map)

    return () => map.remove()
  }, [latitude, longitude, label])

  if (latitude == null || longitude == null) {
    return <div className="map-empty">Waiting for live telemetry or a manually recorded location.</div>
  }

  return <div ref={containerRef} className="maplibre-container" aria-label={label} />
}
