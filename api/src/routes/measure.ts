import { Hono } from 'hono'
import { eq, desc } from 'drizzle-orm'
import { db } from '../db/index.js'
import { measurements, recommendations } from '../db/schema.js'
import { cvMeasure, CVServiceError } from '../lib/cv-client.js'
import { generateMeasurementId } from '../lib/id.js'

const measure = new Hono()

/**
 * POST /v1/measure
 * Full measurement pipeline. Forwards to CV service, stores result, returns with ID.
 * Takes 5–15 seconds depending on image complexity.
 */
measure.post('/', async (c) => {
  let formData: FormData
  try {
    formData = await c.req.formData()
  } catch {
    return c.json({ error: 'validation_error', message: 'Invalid multipart form data' }, 400)
  }

  const image = formData.get('image')
  if (!image || !(image instanceof File)) {
    return c.json({ error: 'validation_error', message: 'image field is required' }, 400)
  }

  if (image.size > 10 * 1024 * 1024) {
    return c.json({ error: 'validation_error', message: 'Image must be under 10MB' }, 400)
  }

  if (!['image/jpeg', 'image/png'].includes(image.type)) {
    return c.json({ error: 'validation_error', message: 'Image must be JPEG or PNG' }, 400)
  }

  const hand = formData.get('hand')
  if (hand && !['left', 'right'].includes(String(hand))) {
    return c.json({ error: 'validation_error', message: 'hand must be "left" or "right"' }, 400)
  }

  // Forward to CV service
  const cvForm = new FormData()
  cvForm.append('image', image)
  if (hand) cvForm.append('hand', String(hand))

  let cvResult
  try {
    cvResult = await cvMeasure(cvForm)
  } catch (err) {
    if (err instanceof CVServiceError) {
      return c.json({ error: err.code, message: err.message }, err.status as 400 | 503)
    }
    throw err
  }

  // Generate ID and store in DB
  const id = generateMeasurementId()
  // TODO: upload image to R2/S3 and store real key (Phase 2 storage)
  const imageKey = `uploads/${id}/original.jpg`
  const debugImageKey = cvResult.debug_image_key ?? null

  await db.insert(measurements).values({
    id,
    imageKey,
    debugImageKey,
    hand: cvResult.hand,
    scalePxPerMm: cvResult.scale_px_per_mm,
    fingers: cvResult.fingers,
    overallConfidence: cvResult.overall_confidence,
    warnings: cvResult.warnings,
    metadata: {},
  })

  return c.json(
    {
      id,
      hand: cvResult.hand,
      scale_px_per_mm: cvResult.scale_px_per_mm,
      fingers: cvResult.fingers,
      overall_confidence: cvResult.overall_confidence,
      debug_image_url: null, // TODO: generate signed URL when R2/S3 is configured
      warnings: cvResult.warnings,
      created_at: new Date().toISOString(),
    },
    200
  )
})

/**
 * GET /v1/measure/history
 * List measurements linked to a Shopify customer. Phase 1: returns empty until
 * Phase 3 links measurements to customer accounts.
 */
measure.get('/history', async (c) => {
  const customerId = c.req.query('customer_id')

  if (!customerId) {
    return c.json({ error: 'validation_error', message: 'customer_id query param is required' }, 400)
  }

  // Find recommendations linked to this customer, ordered newest first
  const rows = await db
    .select({
      measurementId: recommendations.measurementId,
      sizeProfile: recommendations.sizeProfile,
      createdAt: recommendations.createdAt,
    })
    .from(recommendations)
    .where(eq(recommendations.shopifyCustomerId, customerId))
    .orderBy(desc(recommendations.createdAt))

  const measurementIds = rows.map((r) => r.measurementId)
  const activeId = measurementIds[0] ?? null

  // Fetch full measurement records
  const measurementRows =
    measurementIds.length > 0
      ? await Promise.all(
          measurementIds.map((id) =>
            db.select().from(measurements).where(eq(measurements.id, id)).then((r) => r[0])
          )
        )
      : []

  return c.json({
    measurements: measurementRows.filter(Boolean).map((m) => ({
      id: m.id,
      hand: m.hand,
      scale_px_per_mm: m.scalePxPerMm,
      fingers: m.fingers,
      overall_confidence: m.overallConfidence,
      warnings: m.warnings,
      created_at: m.createdAt,
    })),
    active_id: activeId,
  })
})

/**
 * GET /v1/measure/:id
 * Retrieve a specific measurement by ID.
 * Must be defined AFTER /history to avoid shadowing.
 */
measure.get('/:id', async (c) => {
  const id = c.req.param('id')

  const rows = await db.select().from(measurements).where(eq(measurements.id, id))
  const m = rows[0]

  if (!m) {
    return c.json({ error: 'not_found', message: 'Measurement not found' }, 404)
  }

  return c.json({
    id: m.id,
    hand: m.hand,
    scale_px_per_mm: m.scalePxPerMm,
    fingers: m.fingers,
    overall_confidence: m.overallConfidence,
    debug_image_url: null, // TODO: signed URL
    warnings: m.warnings,
    created_at: m.createdAt,
  })
})

export default measure
