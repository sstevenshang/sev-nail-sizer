/**
 * Vitest setup: set env vars before any imports touch process.env.
 */
process.env.JWT_SECRET = 'test-jwt-secret-that-is-at-least-32-chars-long'
process.env.JWT_REFRESH_SECRET = 'test-jwt-refresh-secret-that-is-at-least-32-chars'
process.env.DATABASE_URL = 'postgresql://fake:fake@localhost:5432/fake'
process.env.CV_SERVICE_URL = 'http://localhost:9999'
process.env.PORT = '0'
