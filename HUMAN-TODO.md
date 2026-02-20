# What I Need From Steven

Things only a human can do. Ordered by when I'll need them.

## Before Phase 1 (need ASAP)

### 📸 Test Photos (blocks development)
**Two photos per hand** (can't fit all 5 fingers on a card at once):
- [ ] **Photo A:** Index, middle, ring, pinky placed flat on a credit card
- [ ] **Photo B:** Thumb placed flat on the same credit card
- [ ] Take from ~12" directly above with phone camera
- [ ] Good lighting (natural light or bright room)
- [ ] Try both hands if possible
- [ ] At least one set with a dark-colored card, one with a light card
- [ ] Fingers spread slightly (nails clearly visible, not overlapping)

### 📏 Ground Truth Measurements (blocks accuracy validation)
- [ ] For at least **2 hands** in the photos above, measure each nail with a ruler or calipers:
  - Width at widest point near cuticle (mm)
  - Length from cuticle line to free edge (mm)
- [ ] Record in a simple CSV: `photo_filename, finger, width_mm, length_mm`
- [ ] Doesn't need to be super precise — ±0.5mm is fine

### 💅 Sev Product Info (blocks Phase 2)
- [ ] **How many nail sizes** does Sev offer? (Standard is 0-9)
- [ ] **Width of each size** in mm (measure with calipers if possible)
- [ ] Sold as **pre-made sets, individual sizes, or both**?
- [ ] Between-sizes preference: **size up or size down**?
- [ ] What nail shapes? (coffin, almond, square, stiletto, etc.)
- [ ] Are there different size charts per shape, or one universal chart?

## Before Phase 2

### 💅 Sev Product Info (blocks size chart setup)
- [ ] **How many nail sizes** does Sev offer? (Standard is 0-9)
- [ ] **Width of each size** in mm (measure with calipers if possible)
- [ ] Sold as **pre-made sets, individual sizes, or both**?
- [ ] Between-sizes preference: **size up or size down**?
- [ ] What nail shapes? (coffin, almond, square, stiletto, etc.)
- [ ] Are there different size charts per shape, or one universal chart?

### 🔑 Access & Accounts
- [ ] **Shopify store admin access** (or collaborator invite)
- [ ] Confirm: are **customer accounts** enabled on the store?
- [ ] What **Shopify theme** is Sev using?

### 🎨 Design Preferences
- [ ] Brand colors / style guide for the admin panel (or "just make it clean")
- [ ] Any specific UX preferences for the sizer flow?

## Before Phase 3

### 🏪 Shopify Integration
- [ ] **Shopify Partner account** (needed to create a custom app) — or I can walk you through setting one up
- [ ] Where should the sizer link live? (navigation menu, product pages, standalone page, all of the above?)
- [ ] Product page layout preference for the size recommendation banner

### 📸 Edge Case Photos (improves accuracy)
- [ ] **3-5 more photos** with challenging conditions:
  - Painted nails / nail polish
  - Different skin tones (ask friends/family?)
  - Slightly off-angle (not perfectly top-down)
  - Dim lighting
- [ ] These help us understand where the pipeline breaks

## Ongoing

### 🧪 Testing & Feedback
- [ ] Test the pipeline once MVP is up — does the sizing feel right?
- [ ] Compare recommendations to what you'd pick by hand
- [ ] Flag any measurements that seem off (helps calibrate curve adjustment)

### 📋 Decisions I'll Need Along the Way
- Photo storage: keep originals forever, or delete after processing?
- Processing time: 5-15 seconds acceptable?
- MVP scope: any features to cut or add?

---

**Bottom line:** The #1 blocker right now is **test photos + nail measurements**. Everything else can wait. 5 photos and a ruler gets us started.
