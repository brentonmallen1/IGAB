/**
 * Shrinking a photo before it leaves the phone.
 *
 * A modern iPhone photo is 3-5MB at ~4000px. The receipt pipeline never uses
 * that: the vision model is handed 1536px (MODEL_IMAGE_MAX_DIM) and the stored
 * archive is capped at 4096px. So a full-resolution upload spends a minute of
 * cellular uplink on pixels that are discarded on arrival — and a slow upload
 * is the one most likely to fail, which is when receipts get lost.
 *
 * 2048px is chosen to sit above the model's 1536 (extraction is unaffected)
 * while still being far past legibility for a receipt, and it cuts a typical
 * photo by roughly 85%.
 */
const UPLOAD_MAX_DIM = 2048
const UPLOAD_JPEG_QUALITY = 0.85

/** Dimensions after fitting inside `max`, preserving aspect. Pure. */
export function fitWithin(
  width: number,
  height: number,
  max: number = UPLOAD_MAX_DIM
): { width: number; height: number } {
  if (width <= 0 || height <= 0) return { width, height }
  const longest = Math.max(width, height)
  if (longest <= max) return { width, height }
  const scale = max / longest
  return { width: Math.round(width * scale), height: Math.round(height * scale) }
}

/** Whether shrinking this file is worth attempting at all. */
export function shouldDownscale(file: File): boolean {
  // PDFs are already compact and re-encoding one to JPEG would throw away
  // every page after the first.
  if (file.type === 'application/pdf') return false
  if (!file.type.startsWith('image/')) return false
  // Anything already this small is not what's costing upload time.
  return file.size > 512 * 1024
}

/**
 * Best-effort downscale. Returns the ORIGINAL file whenever anything is
 * uncertain — an unreadable format (HEIC outside Safari), a canvas failure, or
 * a result that isn't actually smaller. Never returning a degraded or empty
 * file matters more than the bandwidth saving.
 */
export async function downscaleForUpload(file: File): Promise<File> {
  if (!shouldDownscale(file)) return file
  if (typeof createImageBitmap !== 'function' || typeof document === 'undefined') return file

  try {
    // `from-image` applies the EXIF rotation, so the bytes we upload are
    // already upright. The server corrects orientation too; this just means
    // there is nothing left for it to correct.
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    const { width, height } = fitWithin(bitmap.width, bitmap.height)
    if (width === bitmap.width && height === bitmap.height) {
      bitmap.close()
      return file
    }

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      bitmap.close()
      return file
    }
    ctx.drawImage(bitmap, 0, 0, width, height)
    bitmap.close()

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', UPLOAD_JPEG_QUALITY)
    )
    if (!blob || blob.size >= file.size) return file

    return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', {
      type: 'image/jpeg',
      lastModified: file.lastModified,
    })
  } catch {
    // HEIC on a browser that can't decode it, an OOM on a huge image, a
    // tainted canvas — upload what the user actually picked.
    return file
  }
}
