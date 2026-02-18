import { customAlphabet } from 'nanoid'

// URL-safe lowercase alphanumeric, 12 chars → 36^12 ≈ 4.7 × 10^18 IDs
const generate = customAlphabet('0123456789abcdefghijklmnopqrstuvwxyz', 12)

export function generateMeasurementId(): string {
  return `msr_${generate()}`
}
