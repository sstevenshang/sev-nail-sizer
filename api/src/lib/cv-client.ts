/**
 * HTTP client for the Python CV service.
 * The CV service runs on CV_SERVICE_URL (default: http://localhost:8000).
 */

export interface FingerMeasurement {
  width_mm: number
  length_mm: number
  curve_adj_width_mm: number
  confidence: number
}

export interface CVValidateResponse {
  valid: boolean
  checks: {
    card_detected: boolean
    hand_detected: boolean
    image_quality: 'good' | 'fair' | 'poor'
    blur_score: number
    brightness: 'dark' | 'normal' | 'bright'
  }
  guidance: string | null
}

export interface CVMeasureResponse {
  hand: 'left' | 'right'
  scale_px_per_mm: number
  fingers: {
    thumb: FingerMeasurement
    index: FingerMeasurement
    middle: FingerMeasurement
    ring: FingerMeasurement
    pinky: FingerMeasurement
  }
  overall_confidence: number
  warnings: string[]
  debug_image_key?: string
}

export class CVServiceError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string
  ) {
    super(message)
    this.name = 'CVServiceError'
  }
}

function cvUrl(path: string): string {
  const base = (process.env.CV_SERVICE_URL ?? 'http://localhost:8000').replace(/\/$/, '')
  return `${base}${path}`
}

async function handleCVResponse<T>(res: Response): Promise<T> {
  if (res.ok) return res.json() as Promise<T>

  let body: Record<string, unknown> = {}
  try {
    body = (await res.json()) as Record<string, unknown>
  } catch {
    // non-JSON error body
  }

  throw new CVServiceError(
    res.status,
    (body.error as string) ?? 'cv_error',
    (body.message as string) ?? `CV service returned ${res.status}`
  )
}

export async function cvValidate(formData: FormData): Promise<CVValidateResponse> {
  let res: Response
  try {
    res = await fetch(cvUrl('/validate'), { method: 'POST', body: formData })
  } catch (err) {
    throw new CVServiceError(503, 'cv_unavailable', 'CV service is unavailable')
  }
  return handleCVResponse<CVValidateResponse>(res)
}

export async function cvMeasure(formData: FormData): Promise<CVMeasureResponse> {
  let res: Response
  try {
    res = await fetch(cvUrl('/measure'), { method: 'POST', body: formData })
  } catch (err) {
    throw new CVServiceError(503, 'cv_unavailable', 'CV service is unavailable')
  }
  return handleCVResponse<CVMeasureResponse>(res)
}
