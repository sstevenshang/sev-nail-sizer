import 'dotenv/config'
import { serve } from '@hono/node-server'
import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { logger } from 'hono/logger'
import { CVServiceError } from './lib/cv-client.js'
import { createRateLimiter } from './middleware/rate-limit.js'
import measureRoutes from './routes/measure.js'
import validateRoutes from './routes/validate.js'
import recommendRoutes from './routes/recommend.js'
import adminRoutes from './routes/admin.js'

const app = new Hono()

// ─── CORS ──────────────────────────────────────────────────────────────────────
const allowedOrigins = (process.env.CORS_ORIGINS ?? '')
  .split(',')
  .map((o) => o.trim())
  .filter(Boolean)

app.use(
  '/*',
  cors({
    origin: allowedOrigins.length > 0 ? allowedOrigins : '*',
    allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'Authorization'],
    exposeHeaders: ['X-RateLimit-Limit', 'X-RateLimit-Remaining'],
    maxAge: 86400,
    credentials: true,
  })
)

// ─── Request logging ───────────────────────────────────────────────────────────
app.use('/*', logger())

// ─── Rate limiting ─────────────────────────────────────────────────────────────
// Public endpoints: 10 req/min per IP
app.use('/v1/measure/*', createRateLimiter(10, 60_000))
app.use('/v1/validate', createRateLimiter(10, 60_000))
app.use('/v1/recommend', createRateLimiter(10, 60_000))
// Admin endpoints: 100 req/min per IP
app.use('/v1/admin/*', createRateLimiter(100, 60_000))

// ─── Routes ────────────────────────────────────────────────────────────────────
app.route('/v1/measure', measureRoutes)
app.route('/v1/validate', validateRoutes)
app.route('/v1/recommend', recommendRoutes)
app.route('/v1/admin', adminRoutes)

// ─── Health check ──────────────────────────────────────────────────────────────
app.get('/health', (c) => c.json({ status: 'ok', timestamp: new Date().toISOString() }))

// ─── 404 ───────────────────────────────────────────────────────────────────────
app.notFound((c) =>
  c.json({ error: 'not_found', message: `No endpoint at ${c.req.method} ${c.req.path}` }, 404)
)

// ─── Global error handler ──────────────────────────────────────────────────────
app.onError((err, c) => {
  console.error(`[error] ${c.req.method} ${c.req.path}`, err)

  if (err instanceof CVServiceError) {
    return c.json({ error: err.code, message: err.message }, err.status as 400 | 503)
  }

  return c.json(
    { error: 'internal_error', message: 'An unexpected error occurred' },
    500
  )
})

// ─── Start server ──────────────────────────────────────────────────────────────
const port = Number(process.env.PORT ?? 3000)

serve(
  {
    fetch: app.fetch,
    port,
    // Allow up to 10MB request bodies for image uploads
    maxRequestBodySize: 10 * 1024 * 1024 + 4096, // 10MB + form overhead
  },
  (info) => {
    console.log(`API server running on http://localhost:${info.port}`)
  }
)

export default app
