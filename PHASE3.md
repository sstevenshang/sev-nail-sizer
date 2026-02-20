# Phase 3: Shopify Integration & Consumer UX

Connect the measurement pipeline to Sev's Shopify store. Customers measure once, get size recommendations on every product page.

## Architecture

```
Customer visits sev.myshopify.com
  → /apps/nail-sizer (App Proxy → our Next.js frontend)
  → Guided photo flow → calls Phase 1 API
  → Results + size recs (using Phase 2 rules) → stored in customer metafields
  → Product pages show "Your size: 3-5-4-6-8" via Theme App Extension
```

## Shopify App Setup

### App Type: Custom App (unlisted)
- **App Bridge 4** for embedded admin views
- **App Proxy** for storefront-facing sizer tool
- **Theme App Extension** for product page integration
- **Customer Account API** for auth (no separate login)

### Required Scopes
```
read_customers, write_customers          # metafields
read_products                            # product data for size mapping
read_customer_account_api                # storefront auth
```

### App Proxy Configuration
```
Subpath prefix: /apps
Subpath: nail-sizer
Proxy URL: https://sev-sizer.vercel.app/storefront
```

Customer visits `sev.myshopify.com/apps/nail-sizer` → proxied to our app with Shopify session context.

## Customer Metafields

```
Namespace: sev_nails
Key: size_profile       → "3-5-4-6-8" (thumb-index-middle-ring-pinky)
Key: measurements       → JSON blob of full measurement data
Key: measured_at        → ISO timestamp
Key: measurement_id     → msr_xxx (reference to our DB)
```

**Metafield definitions** registered via Admin API on app install:
```graphql
mutation {
  metafieldDefinitionCreate(definition: {
    name: "Nail Size Profile"
    namespace: "sev_nails"
    key: "size_profile"
    type: "single_line_text_field"
    ownerType: CUSTOMER
    access: { storefront: READ }
  }) { ... }
}
```

## Consumer UX Flow

### Sizer Flow (at /apps/nail-sizer)

**Two-photo flow** — a credit card can't fit all 5 fingers at once, so users take two photos: one with 4 fingers (index–pinky) and one with thumb.

```
┌──────────────────────────────────────────┐
│         💅 Find Your Nail Size           │
│                                          │
│  Just 2 quick photos with a credit card  │
│  — takes under a minute!                 │
│                                          │
│          ┌─────────────────┐             │
│          │  Let's Start →  │             │
│          └─────────────────┘             │
└──────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────┐
│   📸 Photo 1 of 2: Four Fingers         │
│                                          │
│  Place your INDEX through PINKY fingers  │
│  flat on the credit card.                │
│                                          │
│  ┌────────────────────────────┐          │
│  │   [camera viewfinder]      │          │
│  │   overlay: card outline    │          │
│  │   + 4-finger silhouette    │          │
│  └────────────────────────────┘          │
│                                          │
│  ✅ Card detected                        │
│  ✅ Hand detected (4 fingers)            │
│  ⏳ Analyzing...                         │
│                                          │
│  ✅ Done! Index, Middle, Ring, Pinky     │
│     measured.                            │
│                                          │
│          [Next: Thumb Photo →]           │
└──────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────┐
│   📸 Photo 2 of 2: Thumb                │
│                                          │
│  Now place your THUMB flat on the card.  │
│                                          │
│  ┌────────────────────────────┐          │
│  │   [camera viewfinder]      │          │
│  │   overlay: card outline    │          │
│  │   + thumb silhouette       │          │
│  └────────────────────────────┘          │
│                                          │
│  ✅ Card detected                        │
│  ✅ Thumb detected                       │
│  ⏳ Analyzing...                         │
└──────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────┐
│         ✨ Your Nail Sizes               │
│                                          │
│  👍 Thumb:  Size 3  (17.8mm)            │
│  👆 Index:  Size 5  (15.2mm)            │
│  🖕 Middle: Size 4  (16.0mm)            │
│  💍 Ring:   Size 6  (14.2mm)            │
│  🤙 Pinky:  Size 8  (11.8mm)            │
│                                          │
│  Your profile: 3-5-4-6-8                │
│                                          │
│  [Save to My Account]  [Retake Photos]  │
│                                          │
│  ───────────────────────────             │
│  💡 Saved! You'll see size recs on      │
│     every product page now.              │
└──────────────────────────────────────────┘
```

### Real-time Validation
Before submitting, use the `/validate` endpoint to give live feedback:
- "Move the card fully into frame"
- "Spread your fingers a bit more"
- "Better lighting needed"

### Mobile Camera
- Use `navigator.mediaDevices.getUserMedia` for direct camera access
- Overlay guide on viewfinder (semi-transparent card + hand outline)
- Auto-capture when card + hand both detected (via client-side lightweight check)

## Theme App Extension

Injects a size recommendation banner on product pages.

### Block: `nail-size-banner.liquid`
```liquid
{% if customer and customer.metafields.sev_nails.size_profile %}
  <div class="sev-size-banner">
    <p>💅 Your size: <strong>{{ customer.metafields.sev_nails.size_profile }}</strong></p>
    <p class="sev-size-detail">
      {% assign sizes = customer.metafields.sev_nails.size_profile | split: '-' %}
      Thumb: {{ sizes[0] }} · Index: {{ sizes[1] }} · Middle: {{ sizes[2] }} · Ring: {{ sizes[3] }} · Pinky: {{ sizes[4] }}
    </p>
  </div>
{% else %}
  <div class="sev-size-banner sev-size-cta">
    <p>💅 <a href="/apps/nail-sizer">Find your perfect nail size</a> — takes 30 seconds!</p>
  </div>
{% endif %}
```

### Auto-Select Variant
If products have size variants, auto-select the matching set:
```javascript
// Theme app extension JS
const profile = window.sevNailProfile; // from metafield
if (profile) {
  const matchingVariant = variants.find(v => v.option1 === profile);
  if (matchingVariant) selectVariant(matchingVariant.id);
}
```

## Integration: Sizer → Size Mapping → Recommendation

```
Measurement (Phase 1)
  → curve_adj_width_mm per finger
  → Apply size_rules (Phase 2) → size_number per finger
  → Compose profile string: "3-5-4-6-8"
  → Match to size_sets if pre-packaged
  → Write to customer metafield
  → Product pages read metafield → show recommendation
```

### Recommendation API
```
POST /api/v1/recommend
{
  "measurement_id": "msr_abc123",
  "shopify_customer_id": "gid://shopify/Customer/12345"
}

Response:
{
  "size_profile": "3-5-4-6-8",
  "per_finger": {
    "thumb": { "size": 3, "width_mm": 17.8, "fit": "snug" },
    ...
  },
  "matching_sets": [
    { "set_name": "Medium Set", "shopify_variant_id": "gid://..." }
  ],
  "metafield_written": true
}
```

## Shopify App Structure

```
sev-nail-sizer/
├── shopify-app/                    # Shopify app (Remix template)
│   ├── app/
│   │   ├── routes/
│   │   │   ├── app._index.tsx      # Admin dashboard (embedded)
│   │   │   ├── app.settings.tsx    # App settings
│   │   │   └── storefront.$.tsx    # App proxy handler
│   │   ├── shopify.server.ts       # Shopify API client
│   │   └── lib/
│   │       ├── metafields.ts       # Read/write customer metafields
│   │       └── sizer-api.ts        # Call Phase 1 + 2 APIs
│   ├── extensions/
│   │   └── nail-size-banner/       # Theme app extension
│   │       ├── blocks/
│   │       │   └── size-banner.liquid
│   │       ├── assets/
│   │       │   └── size-banner.css
│   │       └── shopify.extension.toml
│   ├── shopify.app.toml
│   └── package.json
├── storefront/                     # Customer-facing sizer UI
│   ├── src/
│   │   ├── app/
│   │   │   └── page.tsx            # Main sizer flow
│   │   ├── components/
│   │   │   ├── camera-capture.tsx
│   │   │   ├── guide-overlay.tsx
│   │   │   ├── results-display.tsx
│   │   │   └── save-profile.tsx
│   │   └── lib/
│   │       ├── api.ts              # Call measure + recommend APIs
│   │       └── shopify-context.ts  # Read Shopify session from proxy
│   └── package.json
```

## Task Breakdown

| # | Task | Effort |
|---|------|--------|
| 1 | Shopify app scaffold (Remix template, `shopify app init`) | 2h |
| 2 | App proxy setup + storefront routing | 3h |
| 3 | Customer auth via Shopify session | 3h |
| 4 | Guided camera/upload UI | 6h |
| 5 | Camera overlay (card + hand guide) | 4h |
| 6 | Real-time validation feedback | 3h |
| 7 | Results display page | 3h |
| 8 | Recommendation API (measurement → size mapping → profile) | 4h |
| 9 | Customer metafield write/read | 2h |
| 10 | Theme app extension (size banner) | 3h |
| 11 | Auto-select variant on product page | 2h |
| 12 | Embedded admin view (link to Phase 2 admin) | 2h |
| 13 | Mobile responsiveness + camera polish | 4h |
| 14 | End-to-end testing (upload → measure → save → product page) | 4h |
| **Total** | | **~45h (~1.5 weeks)** |

## Timeline Summary

| Phase | Effort | Cumulative |
|-------|--------|------------|
| Phase 1: CV Backend | ~1 week | 1 week |
| Phase 2: Admin Panel | ~4 days | ~2 weeks |
| Phase 3: Shopify + UX | ~1.5 weeks | ~3.5 weeks |

## Open Questions
1. Does Sev have customer accounts enabled? (Required for metafields)
   - *If not, fall back to localStorage + optional account linking*
2. Which Shopify theme? (Affects theme extension compatibility)
3. Pre-packaged sets only, or custom per-customer sets too?
4. Do we need "measure both hands" or just dominant hand?
   - *Rec: just one hand for MVP — press-on nails are usually symmetric*
