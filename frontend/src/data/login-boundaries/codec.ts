export type EncodedBoundary = { n: string; g: string[][][] }

export type LoginBoundaryFeature = {
  type: 'Feature'
  properties: { name: string }
  geometry: {
    type: 'Polygon' | 'MultiPolygon'
    coordinates: number[][][] | number[][][][]
  }
}

function decodeValue(encoded: string, cursor: { index: number }) {
  let result = 0
  let shift = 0
  let byte = 0
  do {
    byte = encoded.charCodeAt(cursor.index++) - 63
    result |= (byte & 0x1f) << shift
    shift += 5
  } while (byte >= 0x20)
  return (result & 1) ? ~(result >> 1) : (result >> 1)
}

function decodeRing(encoded: string) {
  const cursor = { index: 0 }
  const coordinates: number[][] = []
  let lat = 0
  let lng = 0
  while (cursor.index < encoded.length) {
    lat += decodeValue(encoded, cursor)
    lng += decodeValue(encoded, cursor)
    coordinates.push([lng / 100000, lat / 100000])
  }
  return coordinates
}

export function decodeBoundaries(data: EncodedBoundary[]): LoginBoundaryFeature[] {
  return data.map((boundary) => {
    const polygons = boundary.g.map((polygon) => polygon.map(decodeRing))
    return {
      type: 'Feature',
      properties: { name: boundary.n },
      geometry: polygons.length === 1
        ? { type: 'Polygon', coordinates: polygons[0] }
        : { type: 'MultiPolygon', coordinates: polygons },
    }
  })
}
