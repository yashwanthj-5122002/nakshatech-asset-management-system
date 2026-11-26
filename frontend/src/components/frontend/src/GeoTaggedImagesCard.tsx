import { useEffect, useId, useRef, useState, type ChangeEvent } from 'react'
import * as exifr from 'exifr'
import './geo-tagged-images-card.css'

/** Keep the original File: its EXIF metadata must not be stripped before upload. */
export type GeoTaggedImage = {
  file: File
  latitude: number
  longitude: number
  /** Source camera clock, as displayed locally; EXIF often has no timezone. */
  photoTime: string | null
}

type Props = {
  phase: 'start' | 'end'
  images: GeoTaggedImage[]
  onChange: (images: GeoTaggedImage[]) => void
  maxImages?: number
  required?: boolean
  disabled?: boolean
}

const MAX_IMAGE_BYTES = 15 * 1024 * 1024

function cameraTime(value: unknown): string | null {
  if (!(value instanceof Date) || !Number.isFinite(value.getTime())) return null
  const pad = (n: number) => String(n).padStart(2, '0')
  return [value.getFullYear(), pad(value.getMonth() + 1), pad(value.getDate())].join('-') +
    ' ' + [pad(value.getHours()), pad(value.getMinutes()), pad(value.getSeconds())].join(':')
}

function ImageTile({
  image,
  index,
  disabled,
  onRemove,
}: {
  image: GeoTaggedImage
  index: number
  disabled: boolean
  onRemove: () => void
}) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewFailed, setPreviewFailed] = useState(false)

  useEffect(() => {
    const url = URL.createObjectURL(image.file)
    setPreviewUrl(url)
    setPreviewFailed(false)
    return () => URL.revokeObjectURL(url)
  }, [image.file])

  return (
    <article className="naksha-geo-images__tile">
      <div className="naksha-geo-images__thumbnail">
        {previewUrl && !previewFailed ? (
          <img
            src={previewUrl}
            alt={`Geotagged evidence ${index + 1}`}
            onError={() => setPreviewFailed(true)}
          />
        ) : (
          <span>Preview unavailable</span>
        )}
      </div>
      <div className="naksha-geo-images__tile-content">
        <div className="naksha-geo-images__filename" title={image.file.name}>
          {image.file.name}
        </div>
        <div className="naksha-geo-images__success">GPS metadata found</div>
        <div className="naksha-geo-images__coords">
          {image.latitude.toFixed(6)}, {image.longitude.toFixed(6)}
        </div>
        {image.photoTime && (
          <div className="naksha-geo-images__time">Camera time: {image.photoTime}</div>
        )}
        <button
          className="naksha-geo-images__remove"
          type="button"
          onClick={onRemove}
          disabled={disabled}
          aria-label={`Remove ${image.file.name}`}
        >
          Remove
        </button>
      </div>
    </article>
  )
}

/** No navigator.geolocation is used: location comes ONLY from the photo EXIF. */
export function GeoTaggedImagesCard({
  phase,
  images,
  onChange,
  maxImages = 5,
  required = true,
  disabled = false,
}: Props) {
  const inputId = useId()
  const requestId = useRef(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const label = phase === 'start' ? 'Geotagged Start Images' : 'Geotagged End Images'
  const atLimit = images.length >= maxImages
  const blocked = disabled || busy || atLimit

  useEffect(() => () => { requestId.current += 1 }, [])

  async function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = '' // Allow reselecting the same file
    if (selected.length === 0 || busy || disabled) return

    const currentRequest = ++requestId.current
    const remaining = Math.max(0, maxImages - images.length)
    if (remaining === 0) return

    setBusy(true)
    setError('')
    const accepted: GeoTaggedImage[] = []
    const skipped: string[] = []
    if (selected.length > remaining) {
      skipped.push(`Only ${remaining} more image(s) can be added.`)
    }

    for (const file of selected.slice(0, remaining)) {
      const imageType = file.type.startsWith('image/') || /\.(jpe?g|png|heic|heif|tiff?)$/i.test(file.name)
      if (!imageType) {
        skipped.push(`${file.name}: not an image.`)
        continue
      }
      if (file.size > MAX_IMAGE_BYTES) {
        skipped.push(`${file.name}: exceeds 15 MB.`)
        continue
      }
      try {
        const gps = await exifr.gps(file)
        if (currentRequest !== requestId.current) return
        const latitude = gps?.latitude
        const longitude = gps?.longitude
        if (
          typeof latitude !== 'number' || !Number.isFinite(latitude) || latitude < -90 || latitude > 90 ||
          typeof longitude !== 'number' || !Number.isFinite(longitude) || longitude < -180 || longitude > 180
        ) {
          skipped.push(`${file.name}: no valid GPS geotag. Upload the original camera photo with location tags enabled.`)
          continue
        }

        const exif = (await exifr.parse(file, ['DateTimeOriginal', 'CreateDate'])) as
          | { DateTimeOriginal?: unknown; CreateDate?: unknown }
          | undefined
        if (currentRequest !== requestId.current) return
        accepted.push({
          file,
          latitude,
          longitude,
          photoTime: cameraTime(exif?.DateTimeOriginal ?? exif?.CreateDate),
        })
      } catch {
        skipped.push(`${file.name}: GPS metadata could not be read.`)
      }
    }

    if (currentRequest !== requestId.current) return
    if (accepted.length > 0) onChange([...images, ...accepted])
    if (skipped.length > 0) setError(skipped.join(' '))
    setBusy(false)
  }

  return (
    <section className="naksha-geo-images" aria-label={label}>
      <div className="naksha-geo-images__header">
        <div>
          <h3>
            {label} {required && <span aria-label="required">*</span>}
          </h3>
          <p>Add original photos containing GPS location tags.</p>
        </div>
        <label
          htmlFor={inputId}
          className={`naksha-geo-images__add${blocked ? ' naksha-geo-images__add--disabled' : ''}`}
          aria-disabled={blocked}
        >
          + Add Photos
        </label>
        <input
          className="naksha-geo-images__file-input"
          id={inputId}
          type="file"
          accept="image/jpeg,image/png,image/heic,image/heif,image/tiff"
          multiple
          disabled={blocked}
          onChange={(event: ChangeEvent<HTMLInputElement>) => { void handleFiles(event) }}
        />
      </div>

      <p className="naksha-geo-images__count">
        {busy ? 'Checking photo location tags...' : `${images.length} of ${maxImages} images added`}
      </p>
      {error && <p className="naksha-geo-images__error" role="alert">{error}</p>}
      {images.length > 0 ? (
        <div className="naksha-geo-images__grid">
          {images.map((image, index) => (
            <ImageTile
              key={`${image.file.name}-${image.file.lastModified}-${index}`}
              image={image}
              index={index}
              disabled={disabled || busy}
              onRemove={() => onChange(images.filter((_, i) => i !== index))}
            />
          ))}
        </div>
      ) : (
        <p className="naksha-geo-images__empty">No geotagged images selected yet.</p>
      )}
      <p className="naksha-geo-images__help">
        GPS is read from the image EXIF metadata. No live GPS permission is requested.
        Photos shared through messaging apps may have their GPS metadata removed.
      </p>
    </section>
  )
}
