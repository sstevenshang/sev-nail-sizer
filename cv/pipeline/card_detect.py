"""Credit-card detection via edge/contour detection + perspective transform."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

CARD_WIDTH_MM = 85.6
CARD_HEIGHT_MM = 53.98
CARD_ASPECT_RATIO = CARD_WIDTH_MM / CARD_HEIGHT_MM  # ≈ 1.5857
ASPECT_TOLERANCE = 0.15
MIN_CARD_AREA_FRACTION = 0.05  # card must occupy ≥5% of the image


@dataclass
class CardResult:
    corners: np.ndarray   # shape (4, 2), float32, in tl/tr/br/bl order
    px_per_mm: float
    rectified: np.ndarray  # perspective-corrected card patch
    confidence: float


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Return corners in [top-left, top-right, bottom-right, bottom-left] order."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).ravel()
    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = pts[np.argmin(s)]    # top-left:     min sum
    ordered[2] = pts[np.argmax(s)]    # bottom-right:  max sum
    ordered[1] = pts[np.argmin(diff)] # top-right:     min diff
    ordered[3] = pts[np.argmax(diff)] # bottom-left:   max diff
    return ordered


def perspective_transform(
    image: np.ndarray, corners: np.ndarray
) -> tuple[np.ndarray, int, int]:
    """Warp the card region to a front-facing rectangle."""
    tl, tr, br, bl = corners

    width = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    height = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))

    dst = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    M = cv2.getPerspectiveTransform(corners.astype(np.float32), dst)
    rectified = cv2.warpPerspective(image, M, (width, height))
    return rectified, width, height


def detect_card(image: np.ndarray) -> Optional[CardResult]:
    """
    Detect a credit card in the image.

    Tries Canny edges first, falls back to adaptive threshold + morphological closing.
    Returns CardResult or None.
    """
    h, w = image.shape[:2]
    image_area = h * w

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Primary attempt: Canny
    edges = cv2.Canny(blurred, 50, 150)
    result = _find_card_in_edge_map(image, edges, image_area)
    if result is not None:
        return result

    # Fallback 1: adaptive threshold + closing
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    result = _find_card_in_edge_map(image, closed, image_area)
    if result is not None:
        return result

    # Fallback 2: Otsu binary threshold
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel_large = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    otsu = cv2.morphologyEx(otsu, cv2.MORPH_CLOSE, kernel_large)
    otsu = cv2.morphologyEx(otsu, cv2.MORPH_OPEN, kernel_large)
    result = _find_card_in_edge_map(image, otsu, image_area)
    if result is not None:
        return result

    # Fallback 3: high binary threshold to isolate bright card regions
    for thresh_val in (180, 160, 140):
        _, bright = cv2.threshold(blurred, thresh_val, 255, cv2.THRESH_BINARY)
        result = _find_card_in_edge_map(image, bright, image_area)
        if result is not None:
            return result

    return None


def _find_card_in_edge_map(
    image: np.ndarray, edge_map: np.ndarray, image_area: int
) -> Optional[CardResult]:
    """Search contours in edge_map for a credit-card-shaped quadrilateral."""
    contours, _ = cv2.findContours(
        edge_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    best_corners: Optional[np.ndarray] = None
    best_score = 0.0

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < MIN_CARD_AREA_FRACTION * image_area:
            continue

        # Try approxPolyDP at multiple epsilon levels
        peri = cv2.arcLength(contour, True)
        approx = None
        for eps_mult in (0.02, 0.04, 0.06, 0.08):
            candidate = cv2.approxPolyDP(contour, eps_mult * peri, True)
            if len(candidate) == 4:
                approx = candidate
                break

        if approx is None:
            # Last resort: use minAreaRect corners directly
            rect = cv2.minAreaRect(contour)
            rw, rh = rect[1]
            if rw == 0 or rh == 0:
                continue
            aspect = max(rw, rh) / min(rw, rh)
            if abs(aspect - CARD_ASPECT_RATIO) > ASPECT_TOLERANCE:
                continue
            # Use box points as corners
            box = cv2.boxPoints(rect)
            approx = box.reshape(4, 1, 2).astype(np.float32)
        else:
            rect = cv2.minAreaRect(approx)
            rw, rh = rect[1]
            if rw == 0 or rh == 0:
                continue
            aspect = max(rw, rh) / min(rw, rh)
            if abs(aspect - CARD_ASPECT_RATIO) > ASPECT_TOLERANCE:
                continue

        # Check rectangularity: contour area vs minAreaRect area
        rect_area = rw * rh
        if rect_area > 0:
            rectangularity = area / rect_area
            if rectangularity < 0.7:
                continue

        score = area / image_area
        if score > best_score:
            best_score = score
            best_corners = approx

    if best_corners is None:
        return None

    corners = order_corners(best_corners.reshape(4, 2).astype(np.float32))
    rectified, rect_w, rect_h = perspective_transform(image, corners)

    # px_per_mm from the longer dimension → card width
    px_per_mm = max(rect_w, rect_h) / CARD_WIDTH_MM

    # Confidence: inversely proportional to aspect-ratio error
    rect = cv2.minAreaRect(best_corners)
    rw, rh = rect[1]
    aspect = max(rw, rh) / min(rw, rh)
    aspect_err = abs(aspect - CARD_ASPECT_RATIO) / CARD_ASPECT_RATIO
    confidence = float(max(0.0, 1.0 - aspect_err * 5))

    return CardResult(
        corners=corners,
        px_per_mm=px_per_mm,
        rectified=rectified,
        confidence=confidence,
    )
