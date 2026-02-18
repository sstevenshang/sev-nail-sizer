# API Design

Base URL: `https://api.sev-nails.com/v1` (Railway)

## Auth

**Three auth contexts:**

1. **Public (customer-facing)** — rate-limited by IP, no auth for `/measure` and `/validate`. Results are anonymous until linked to a Shopify customer in Phase 3.

2. **Admin** — JWT-based. Login with email/password → get access + refresh token. All `/admin/*` endpoints require `Authorization: Bearer <token>`. Tokens expire in 24h, refresh tokens in 30d.

3. **Shopify (Phase 3)** — Shopify session tokens via App Bridge. Verified server-side using Shopify's HMAC. Used for customer metafield writes.

### Why no auth on /measure?
It's a stateless image processing endpoint — like an image resize service. Rate limiting (10 req/min per IP) prevents abuse. Adding auth here would add friction to the "try before you sign up" flow. Results get linked to a Shopify customer later when they save.

### Security

- **Rate limiting:** 10 req/min per IP on public endpoints, 100 req/min on admin
- **File validation:** JPEG/PNG only, max 10MB, magic byte check (not just extension)
- **Input sanitization:** all text inputs sanitized, SQL via parameterized queries (Drizzle ORM)
- **CORS:** restricted to Sev's Shopify domain + admin domain
- **HTTPS only** (Railway provides this)
- **Admin passwords:** bcrypt hashed, min 12 chars
- **Image storage:** private bucket, signed URLs for access (expire in 1h)

---

## Endpoints

### Measurement

#### `POST /v1/validate`
Quick pre-check before full measurement. Fast (~1s, no SAM 2 call).

```
Content-Type: multipart/form-data
Body: image (JPEG/PNG, max 10MB)

Response 200:
{
  "valid": true,
  "checks": {
    "card_detected": true,
    "hand_detected": true,
    "image_quality": "good",    // good | fair | poor
    "blur_score": 142,          // >100 = acceptable
    "brightness": "normal"      // dark | normal | bright
  },
  "guidance": null
}

Response 200 (failed validation):
{
  "valid": false,
  "checks": {
    "card_detected": false,
    "hand_detected": true,
    "image_quality": "fair",
    "blur_score": 45,
    "brightness": "dark"
  },
  "guidance": "Place the full credit card in the frame with better lighting"
}
```

#### `POST /v1/measure`
Full measurement pipeline. Takes 5-15 seconds.

```
Content-Type: multipart/form-data
Body:
  image: (JPEG/PNG, max 10MB)
  hand: "left" | "right" (optional, auto-detected)

Response 200:
{
  "id": "msr_a1b2c3d4",
  "hand": "right",
  "scale_px_per_mm": 12.4,
  "fingers": {
    "thumb": {
      "width_mm": 16.2,
      "length_mm": 12.1,
      "curve_adj_width_mm": 17.8,
      "confidence": 0.94
    },
    "index": {
      "width_mm": 14.1,
      "length_mm": 11.3,
      "curve_adj_width_mm": 15.2,
      "confidence": 0.92
    },
    "middle": {
      "width_mm": 14.8,
      "length_mm": 12.0,
      "curve_adj_width_mm": 16.0,
      "confidence": 0.95
    },
    "ring": {
      "width_mm": 13.2,
      "length_mm": 10.5,
      "curve_adj_width_mm": 14.2,
      "confidence": 0.91
    },
    "pinky": {
      "width_mm": 11.0,
      "length_mm": 8.8,
      "curve_adj_width_mm": 11.8,
      "confidence": 0.88
    }
  },
  "overall_confidence": 0.92,
  "debug_image_url": "https://storage.../debug/msr_a1b2c3d4.jpg?sig=...",
  "warnings": [],
  "created_at": "2026-02-17T20:00:00Z"
}

Response 400:
{
  "error": "card_not_detected",
  "message": "Could not find a credit card in the image. Place the full card in frame.",
  "guidance": "Ensure all 4 corners of the card are visible"
}
```

#### `GET /v1/measure/:id`
Retrieve a previous measurement.

```
Response 200: (same shape as POST /measure response)

Response 404:
{ "error": "not_found", "message": "Measurement not found" }
```

#### `GET /v1/measure/history?customer_id=...`
List all measurements for a customer (history preserved, profile uses latest).

```json
// Response 200
{
  "measurements": [ ... ],
  "active_id": "msr_a1b2c3d4"  // the one powering current profile
}
```

---

### Size Recommendation (connects Phase 1 → Phase 2)

#### `POST /v1/recommend`
Given a measurement, apply size mapping rules and return recommendations.

```json
// Request
{
  "measurement_id": "msr_a1b2c3d4"
}

// Response 200
{
  "measurement_id": "msr_a1b2c3d4",
  "size_profile": "3-5-4-6-8",
  "per_finger": {
    "thumb":  { "size": 3, "size_label": "Medium-Large", "width_mm": 17.8, "fit": "snug" },
    "index":  { "size": 5, "size_label": "Medium",       "width_mm": 15.2, "fit": "standard" },
    "middle": { "size": 4, "size_label": "Medium",       "width_mm": 16.0, "fit": "standard" },
    "ring":   { "size": 6, "size_label": "Small-Medium",  "width_mm": 14.2, "fit": "snug" },
    "pinky":  { "size": 8, "size_label": "Small",         "width_mm": 11.8, "fit": "standard" }
  },
  "matching_sets": [
    { "set_name": "Medium Set", "set_id": "set_xyz", "exact_match": false, "diff": 1 }
  ]
}

// Response 400 (no size rules configured yet)
{
  "error": "no_rules",
  "message": "Size mapping rules have not been configured. Contact admin."
}
```

---

### Admin — Sizes

#### `GET /v1/admin/sizes`
```json
// Response 200
{
  "sizes": [
    { "id": 1, "size_number": 0, "width_mm": 17.5, "length_mm": 14.0, "label": "Extra Large" },
    { "id": 2, "size_number": 1, "width_mm": 16.5, "length_mm": 13.5, "label": "Large" },
    ...
  ],
  "chart_id": "default"
}
```

#### `POST /v1/admin/sizes`
```json
// Request
{ "size_number": 0, "width_mm": 17.5, "length_mm": 14.0, "label": "Extra Large" }

// Response 201
{ "id": 1, "size_number": 0, "width_mm": 17.5, "length_mm": 14.0, "label": "Extra Large" }
```

#### `PUT /v1/admin/sizes/:id`
#### `DELETE /v1/admin/sizes/:id`

#### `POST /v1/admin/sizes/import`
```
Content-Type: text/csv
Body: size_number,width_mm,length_mm,label\n0,17.5,14.0,Extra Large\n...

Response 200:
{ "imported": 10, "errors": [] }
```

#### `GET /v1/admin/sizes/export`
Returns CSV.

---

### Admin — Size Rules

#### `GET /v1/admin/rules`
```json
{
  "rules": [
    { "id": 1, "finger": "all", "min_width_mm": 17.0, "max_width_mm": 18.5, "mapped_size": 0, "priority": 0 },
    { "id": 2, "finger": "all", "min_width_mm": 15.5, "max_width_mm": 17.0, "mapped_size": 1, "priority": 0 },
    ...
  ],
  "config": {
    "between_sizes": "size_down",   // size_up | size_down
    "tolerance_mm": 0.3
  }
}
```

#### `POST /v1/admin/rules`
#### `PUT /v1/admin/rules/:id`
#### `DELETE /v1/admin/rules/:id`

#### `PUT /v1/admin/rules/config`
```json
{ "between_sizes": "size_down", "tolerance_mm": 0.3 }
```

#### `POST /v1/admin/rules/preview`
Test rules against sample measurements without saving.
```json
// Request
{
  "measurements": {
    "thumb": 17.8, "index": 15.2, "middle": 16.0, "ring": 14.2, "pinky": 11.8
  }
}

// Response 200
{
  "recommended": {
    "thumb": { "size": 3, "label": "Medium-Large" },
    ...
  },
  "size_profile": "3-5-4-6-8"
}
```

---

### Admin — Sets

#### `GET /v1/admin/sets`
#### `POST /v1/admin/sets`
```json
{
  "name": "Medium Set",
  "thumb_size": 3, "index_size": 5, "middle_size": 4, "ring_size": 6, "pinky_size": 8,
  "shopify_variant_id": null
}
```
#### `PUT /v1/admin/sets/:id`
#### `DELETE /v1/admin/sets/:id`

---

### Admin — Measurements (read-only)

#### `GET /v1/admin/measurements`
```
Query params: page, limit, sort, min_confidence, from_date, to_date

Response 200:
{
  "measurements": [ ... ],
  "total": 142,
  "page": 1,
  "pages": 8
}
```

#### `GET /v1/admin/measurements/:id`
Full detail including debug image URL.

#### `GET /v1/admin/measurements/stats`
```json
{
  "total": 142,
  "last_7_days": 23,
  "avg_confidence": 0.91,
  "low_confidence_count": 3,
  "common_warnings": ["partial_nail_occlusion"]
}
```

---

### Admin — Auth

#### `POST /v1/admin/auth/login`
```json
// Request
{ "email": "admin@sev.com", "password": "..." }

// Response 200
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 86400
}
```

#### `POST /v1/admin/auth/refresh`
```json
{ "refresh_token": "eyJ..." }
```

---

### Shopify (Phase 3)

#### `POST /v1/shopify/save-profile`
Called after customer saves their sizing. Writes to Shopify customer metafields.

```json
// Request (Shopify session token in header)
{
  "measurement_id": "msr_a1b2c3d4"
}

// Response 200
{
  "customer_id": "gid://shopify/Customer/12345",
  "size_profile": "3-5-4-6-8",
  "metafields_written": true
}
```

#### `GET /v1/shopify/customer-profile`
Read current customer's saved profile (from Shopify metafields).

```json
// Response 200
{
  "has_profile": true,
  "size_profile": "3-5-4-6-8",
  "measured_at": "2026-02-17T20:00:00Z",
  "measurement_id": "msr_a1b2c3d4"
}

// Response 200 (no profile)
{ "has_profile": false }
```

---

## Error Format (all endpoints)

```json
{
  "error": "error_code",
  "message": "Human-readable description",
  "details": {}   // optional, extra context
}
```

Standard codes: `validation_error`, `not_found`, `unauthorized`, `rate_limited`, `internal_error`, `card_not_detected`, `hand_not_detected`, `image_too_blurry`, `no_rules`.

---

## Design Decisions Log

1. **`/validate` and `/measure` are separate endpoints** — instant feedback before the 15s pipeline wait
2. **Measurement history preserved** — all measurements kept, but customer profile always reflects the latest
3. **No auth on public endpoints** — rate-limited by IP; auth only for admin and Shopify profile saving
4. **Hybrid auth for customers** — localStorage for guests, Shopify metafields when logged in, migrate on account creation
5. **Auto-update existing profiles when size rules change** — background job re-runs recommendations
6. **Mobile-ready** — stateless REST API, URL-based assets, no web-specific assumptions in the API layer
