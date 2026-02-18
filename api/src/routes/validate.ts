import { Hono } from 'hono'
import { cvValidate, CVServiceError } from '../lib/cv-client.js'

const validate = new Hono()

/**
 * POST /v1/validate
 * Quick pre-check before the full measurement pipeline (~1s, no SAM 2 call).
 * Proxies directly to CV service — no DB writes.
 */
validate.post('/', async (c) => {
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

  // Forward to CV service
  const cvForm = new FormData()
  cvForm.append('image', image)

  try {
    const result = await cvValidate(cvForm)
    return c.json(result, 200)
  } catch (err) {
    if (err instanceof CVServiceError) {
      return c.json({ error: err.code, message: err.message }, err.status as 400 | 503)
    }
    throw err
  }
})

export default validate
