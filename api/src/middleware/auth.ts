import type { Context, Next } from 'hono'
import jwt from 'jsonwebtoken'

export interface AdminPayload {
  id: number
  email: string
  type: 'admin'
}

declare module 'hono' {
  interface ContextVariableMap {
    admin: AdminPayload
  }
}

export function requireAdmin() {
  return async (c: Context, next: Next) => {
    const auth = c.req.header('Authorization')

    if (!auth?.startsWith('Bearer ')) {
      return c.json({ error: 'unauthorized', message: 'Missing or invalid Authorization header' }, 401)
    }

    const token = auth.slice(7)
    const secret = process.env.JWT_SECRET

    if (!secret) {
      console.error('JWT_SECRET not configured')
      return c.json({ error: 'internal_error', message: 'Server misconfiguration' }, 500)
    }

    try {
      const payload = jwt.verify(token, secret) as AdminPayload

      if (payload.type !== 'admin') {
        return c.json({ error: 'unauthorized', message: 'Invalid token type' }, 401)
      }

      c.set('admin', payload)
      await next()
    } catch (err) {
      if (err instanceof jwt.TokenExpiredError) {
        return c.json({ error: 'unauthorized', message: 'Token expired' }, 401)
      }
      return c.json({ error: 'unauthorized', message: 'Invalid token' }, 401)
    }
  }
}

export function signAccessToken(payload: Omit<AdminPayload, 'type'>): string {
  const secret = process.env.JWT_SECRET!
  return jwt.sign({ ...payload, type: 'admin' }, secret, { expiresIn: '24h' })
}

export function signRefreshToken(payload: Omit<AdminPayload, 'type'>): string {
  const secret = process.env.JWT_REFRESH_SECRET!
  return jwt.sign({ ...payload, type: 'admin' }, secret, { expiresIn: '30d' })
}

export function verifyRefreshToken(token: string): AdminPayload {
  const secret = process.env.JWT_REFRESH_SECRET!
  return jwt.verify(token, secret) as AdminPayload
}
