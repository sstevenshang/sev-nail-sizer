"""Annotated debug image: card outline, hand landmarks, nail masks, measurements."""

from __future__ import annotations

from typing import Dict, List, Optional

import cv2
import numpy as np

from .card_detect import CardResult
from .hand_detect import HandResult
from .measure import FingerMeasurement
from .nail_segment import NailMask

_GREEN = (0, 255, 0)
_BLUE = (255, 100, 0)
_RED = (0, 0, 255)
_PINK = (180, 0, 220)
_YELLOW = (0, 200, 255)
_WHITE = (255, 255, 255)

_FONT = cv2.FONT_HERSHEY_SIMPLEX


def draw_debug_image(
    image: np.ndarray,
    card_result: Optional[CardResult] = None,
    hand_result: Optional[HandResult] = None,
    nail_masks: Optional[List[NailMask]] = None,
    measurements: Optional[Dict[str, FingerMeasurement]] = None,
) -> np.ndarray:
    """Return an annotated copy of *image*."""
    debug = image.copy()

    if card_result is not None:
        _draw_card(debug, card_result)

    if nail_masks:
        _draw_nail_masks(debug, nail_masks)

    if hand_result is not None:
        _draw_hand(debug, hand_result)

    if measurements is not None and hand_result is not None:
        _draw_measurements(debug, measurements, hand_result)

    return debug


def _draw_card(image: np.ndarray, card: CardResult) -> None:
    corners = card.corners.astype(np.int32).reshape(-1, 1, 2)
    cv2.polylines(image, [corners], isClosed=True, color=_GREEN, thickness=2)
    label_pt = tuple(card.corners[0].astype(int))
    cv2.putText(
        image,
        f"Card {card.px_per_mm:.1f}px/mm",
        label_pt,
        _FONT,
        0.55,
        _GREEN,
        2,
    )


def _draw_hand(image: np.ndarray, hand: HandResult) -> None:
    for x, y in hand.landmarks:
        cv2.circle(image, (x, y), 3, _BLUE, -1)
    for finger, (x, y) in hand.fingertip_positions.items():
        cv2.circle(image, (x, y), 6, _RED, -1)
        cv2.putText(image, finger[0].upper(), (x + 5, y - 6), _FONT, 0.4, _WHITE, 1)


def _draw_nail_masks(image: np.ndarray, masks: List[NailMask]) -> None:
    """Semi-transparent pink overlay for each nail mask."""
    overlay = image.copy()
    for nm in masks:
        if not nm.mask.any():
            continue
        overlay[nm.mask] = _PINK
    cv2.addWeighted(overlay, 0.4, image, 0.6, 0, image)


def _draw_measurements(
    image: np.ndarray,
    measurements: Dict[str, FingerMeasurement],
    hand: HandResult,
) -> None:
    for finger, meas in measurements.items():
        if finger not in hand.fingertip_positions:
            continue
        x, y = hand.fingertip_positions[finger]
        label = f"W{meas.width_mm:.1f} L{meas.length_mm:.1f}mm"
        cv2.putText(image, label, (x + 8, y + 4), _FONT, 0.35, _YELLOW, 1)
