import type { Context, Next } from 'hono'

interface RateLimitEntry {
  count: number
  resetAt: number
}

// In-memory store — sufficient for single-instance. Replace with Redis for multi-instance.
const store = new Map<string, RateLimitEntry>()

// Evict stale entries every 5 minutes to prevent unbounded memory growth
setInterval(() => {
  const now = Date.now()
  for (const [key, entry] of store.entries()) {
    if (now > entry.resetAt) store.delete(key)
  }
}, 5 * 60 * 1000)

function getClientIp(c: Context): string {
  return (
    c.req.header('x-forwarded-for')?.split(',')[0].trim() ??
    c.req.header('x-real-ip') ??
    'unknown'
  )
}

/**
 * createRateLimiter(maxRequests, windowMs)
 *
 * Usage:
 *   app.use('/public/*', createRateLimiter(10, 60_000))   // 10 req/min
 *   app.use('/admin/*',  createRateLimiter(100, 60_000))  // 100 req/min
 */
export function createRateLimiter(maxRequests: number, windowMs: number) {
  return async (c: Context, next: Next) => {
    const ip = getClientIp(c)
    const key = `${ip}:${c.req.path.split('/')[2] ?? 'root'}` // bucket per top-level path segment
    const now = Date.now()

    const entry = store.get(key)

    if (!entry || now > entry.resetAt) {
      store.set(key, { count: 1, resetAt: now + windowMs })
      c.res.headers.set('X-RateLimit-Limit', String(maxRequests))
      c.res.headers.set('X-RateLimit-Remaining', String(maxRequests - 1))
      await next()
      return
    }

    if (entry.count >= maxRequests) {
      const retryAfter = Math.ceil((entry.resetAt - now) / 1000)
      c.res.headers.set('Retry-After', String(retryAfter))
      return c.json(
        { error: 'rate_limited', message: `Too many requests. Try again in ${retryAfter}s.` },
        429
      )
    }

    entry.count++
    c.res.headers.set('X-RateLimit-Limit', String(maxRequests))
    c.res.headers.set('X-RateLimit-Remaining', String(maxRequests - entry.count))
    await next()
  }
}
