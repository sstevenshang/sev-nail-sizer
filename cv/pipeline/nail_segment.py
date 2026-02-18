"""Nail segmentation: OpenCV HSV-based local fallback + SAM 2 (Replicate) for cloud."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

import cv2
import numpy as np

MOCK_ENV_VAR = "SEV_MOCK_SEGMENTATION"
REPLICATE_MODEL = "meta/sam-2"

# Approximate nail dimensions in pixels (for the synthetic mock)
MOCK_NAIL_HALF_W = 15
MOCK_NAIL_HALF_H = 22

# ROI around fingertip to search for nail (as fraction of image height)
ROI_HALF_W_FRAC = 0.05   # half-width of ROI as fraction of image width
ROI_HALF_H_FRAC = 0.06   # half-height of ROI as fraction of image height
ROI_MIN_PX = 20           # minimum ROI half-size in pixels
ROI_MAX_PX = 80           # maximum ROI half-size in pixels


@dataclass
class NailMask:
    finger: str
    mask: np.ndarray   # boolean array, shape == (H, W)
    confidence: float


def segment_nails(
    image: np.ndarray,
    fingertip_positions: Dict[str, Tuple[int, int]],
    mock: bool = False,
) -> List[NailMask]:
    """
    Segment nail regions.

    Priority order:
      1. Synthetic ellipse mock   — if mock=True or SEV_MOCK_SEGMENTATION=1
      2. OpenCV HSV fallback      — local, no network needed (default)
      3. SAM 2 via Replicate      — if REPLICATE_API_TOKEN is set and
                                    SEV_USE_REPLICATE=1

    The OpenCV fallback uses skin-colour detection in HSV space to isolate
    the fingertip region, then refines with GrabCut / contour analysis to
    extract the nail plate.
    """
    if mock or os.environ.get(MOCK_ENV_VAR) == "1":
        return _mock_masks(image, fingertip_positions)

    if os.environ.get("SEV_USE_REPLICATE") == "1" and os.environ.get("REPLICATE_API_TOKEN"):
        return _call_replicate(image, fingertip_positions)

    return _opencv_segment(image, fingertip_positions)


# ---------------------------------------------------------------------------
# Synthetic mock implementation (ellipses)
# ---------------------------------------------------------------------------

def _mock_masks(
    image: np.ndarray,
    fingertip_positions: Dict[str, Tuple[int, int]],
) -> List[NailMask]:
    """Return synthetic elliptical masks centred at each fingertip."""
    h, w = image.shape[:2]
    masks: List[NailMask] = []

    for finger, (fx, fy) in fingertip_positions.items():
        canvas = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(
            canvas,
            (int(fx), int(fy)),
            (MOCK_NAIL_HALF_W, MOCK_NAIL_HALF_H),
            angle=0,
            startAngle=0,
            endAngle=360,
            color=255,
            thickness=-1,
        )
        masks.append(
            NailMask(finger=finger, mask=canvas.astype(bool), confidence=0.9)
        )

    return masks


# ---------------------------------------------------------------------------
# OpenCV HSV-based segmentation (local fallback, no network)
# ---------------------------------------------------------------------------

def _opencv_segment(
    image: np.ndarray,
    fingertip_positions: Dict[str, Tuple[int, int]],
) -> List[NailMask]:
    """
    Segment nails using HSV skin-colour detection within fingertip ROIs.

    Algorithm per finger:
      1. Crop a rectangular ROI around the fingertip.
      2. Convert to HSV and create a skin-colour mask.
      3. Apply morphological ops to clean up the mask.
      4. Within the skin mask, look for the nail plate by searching for
         low-saturation, high-value pixels (nails are lighter / less pigmented
         than surrounding skin).
      5. Pick the largest connected component that overlaps the fingertip.
      6. Project back to full-image coordinates.
    """
    h, w = image.shape[:2]

    # Compute ROI half-sizes clamped to [ROI_MIN_PX, ROI_MAX_PX]
    rw = int(np.clip(w * ROI_HALF_W_FRAC, ROI_MIN_PX, ROI_MAX_PX))
    rh = int(np.clip(h * ROI_HALF_H_FRAC, ROI_MIN_PX, ROI_MAX_PX))

    # Pre-convert full image to HSV once
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    masks: List[NailMask] = []

    for finger, (fx, fy) in fingertip_positions.items():
        # --- 1. Compute ROI bounds, clamped to image boundaries
        x1 = max(0, fx - rw)
        y1 = max(0, fy - rh)
        x2 = min(w, fx + rw)
        y2 = min(h, fy + rh)

        if x2 <= x1 or y2 <= y1:
            masks.append(NailMask(finger=finger, mask=np.zeros((h, w), dtype=bool), confidence=0.0))
            continue

        roi_hsv = hsv[y1:y2, x1:x2]
        roi_bgr = image[y1:y2, x1:x2]

        # --- 2. Skin colour mask in HSV
        skin_mask = _skin_mask_hsv(roi_hsv)

        # --- 3. Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # --- 4. Nail plate: low saturation + high value within skin region
        nail_candidate = _nail_candidate_mask(roi_hsv, skin_mask)

        # --- 5. Largest connected component overlapping fingertip centre
        nail_roi_mask, conf = _largest_component_near_tip(
            nail_candidate, fx - x1, fy - y1
        )

        # Fall back to skin mask centred on tip if nail plate not found
        if nail_roi_mask is None or nail_roi_mask.sum() < 20:
            nail_roi_mask, conf = _largest_component_near_tip(
                skin_mask, fx - x1, fy - y1, radius_frac=0.6
            )
            conf *= 0.5  # lower confidence for skin-only fallback

        # --- 6. Project back to full image
        full_mask = np.zeros((h, w), dtype=bool)
        if nail_roi_mask is not None and nail_roi_mask.sum() > 0:
            full_mask[y1:y2, x1:x2] = nail_roi_mask.astype(bool)

        masks.append(NailMask(finger=finger, mask=full_mask, confidence=float(conf)))

    return masks


def _skin_mask_hsv(roi_hsv: np.ndarray) -> np.ndarray:
    """
    Create a binary mask for skin pixels in an HSV ROI.

    Two ranges cover a wide variety of skin tones:
      - Hue 0–20° (warm reds/oranges) and 340–360° (wrap-around)
      - Saturation 15–170, Value 50–255
    """
    # Range 1: H 0-20
    lower1 = np.array([0,  15,  50], dtype=np.uint8)
    upper1 = np.array([20, 170, 255], dtype=np.uint8)

    # Range 2: H 160-180 (wrap-around reds)
    lower2 = np.array([160, 15,  50], dtype=np.uint8)
    upper2 = np.array([180, 170, 255], dtype=np.uint8)

    mask1 = cv2.inRange(roi_hsv, lower1, upper1)
    mask2 = cv2.inRange(roi_hsv, lower2, upper2)
    return cv2.bitwise_or(mask1, mask2)


def _nail_candidate_mask(roi_hsv: np.ndarray, skin_mask: np.ndarray) -> np.ndarray:
    """
    Within skin pixels, identify nail-plate candidates:
    nails tend to have lower saturation and higher value than surrounding skin.
    """
    # Saturation < 80 AND Value > 140 → likely nail plate (pinkish/light)
    h_ch, s_ch, v_ch = cv2.split(roi_hsv)
    low_sat = (s_ch < 80).astype(np.uint8) * 255
    high_val = (v_ch > 130).astype(np.uint8) * 255
    nail_raw = cv2.bitwise_and(low_sat, high_val)
    # Restrict to skin region (dilated slightly so we don't miss edges)
    skin_dilated = cv2.dilate(skin_mask, np.ones((3, 3), np.uint8), iterations=1)
    return cv2.bitwise_and(nail_raw, skin_dilated)


def _largest_component_near_tip(
    binary_mask: np.ndarray,
    tip_x: int,
    tip_y: int,
    radius_frac: float = 0.8,
) -> Tuple[np.ndarray | None, float]:
    """
    Find the largest connected component in *binary_mask* whose centroid is
    within *radius_frac* of the ROI diagonal from the tip pixel.

    Returns (component_mask, confidence) where confidence ∈ [0, 1].
    """
    if binary_mask is None or binary_mask.sum() == 0:
        return None, 0.0

    n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        binary_mask, connectivity=8
    )

    roi_h, roi_w = binary_mask.shape
    max_radius = radius_frac * np.sqrt(roi_w ** 2 + roi_h ** 2) / 2

    best_mask = None
    best_area = 0
    best_conf = 0.0

    for label in range(1, n_labels):  # skip background (0)
        cx, cy = centroids[label]
        dist = np.sqrt((cx - tip_x) ** 2 + (cy - tip_y) ** 2)
        if dist > max_radius:
            continue
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area > best_area:
            best_area = area
            best_mask = (labels == label).astype(np.uint8)
            # Confidence: larger area relative to ROI → higher confidence
            roi_area = roi_h * roi_w
            best_conf = min(1.0, area / max(roi_area * 0.05, 1))

    return best_mask, best_conf


# ---------------------------------------------------------------------------
# Real Replicate implementation (cloud, requires REPLICATE_API_TOKEN)
# ---------------------------------------------------------------------------

def _call_replicate(
    image: np.ndarray,
    fingertip_positions: Dict[str, Tuple[int, int]],
) -> List[NailMask]:
    """Call meta/sam-2 on Replicate with a point prompt at each fingertip."""
    import base64

    import replicate
    from PIL import Image as PILImage

    h, w = image.shape[:2]

    pil_image = PILImage.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil_image.save(buf, format="JPEG", quality=90)
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    masks: List[NailMask] = []
    for finger, (fx, fy) in fingertip_positions.items():
        try:
            output = replicate.run(
                REPLICATE_MODEL,
                input={
                    "image": f"data:image/jpeg;base64,{img_b64}",
                    "point_coords": [[fx, fy]],
                    "point_labels": [1],
                },
            )
            mask = _parse_replicate_mask(output, h, w)
            masks.append(NailMask(finger=finger, mask=mask, confidence=0.85))
        except Exception:
            masks.append(
                NailMask(
                    finger=finger,
                    mask=np.zeros((h, w), dtype=bool),
                    confidence=0.0,
                )
            )

    return masks


def _parse_replicate_mask(output: object, h: int, w: int) -> np.ndarray:
    """Convert SAM 2 Replicate output to a boolean mask."""
    import requests
    from PIL import Image as PILImage

    if isinstance(output, list) and output:
        mask_url = str(output[0])
    elif isinstance(output, str):
        mask_url = output
    else:
        return np.zeros((h, w), dtype=bool)

    resp = requests.get(mask_url, timeout=30)
    mask_img = PILImage.open(io.BytesIO(resp.content)).convert("L")
    mask_arr = np.array(mask_img.resize((w, h), PILImage.NEAREST))
    return mask_arr > 127
