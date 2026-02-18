"""Extract nail dimensions (px → mm) from segmentation masks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from .nail_segment import NailMask


@dataclass
class FingerMeasurement:
    finger: str
    width_mm: float   # widest horizontal extent of nail
    length_mm: float  # cuticle-to-free-edge extent
    confidence: float


def measure_nail(mask: NailMask, px_per_mm: float) -> FingerMeasurement:
    """
    Compute nail width and length from a binary mask.

    Width  = widest row span across the mask.
    Length = total row span (cuticle row → free-edge row).
    """
    if not mask.mask.any() or px_per_mm <= 0:
        return FingerMeasurement(
            finger=mask.finger,
            width_mm=0.0,
            length_mm=0.0,
            confidence=0.0,
        )

    rows_with_pixels = np.any(mask.mask, axis=1)
    cols_with_pixels = np.any(mask.mask, axis=0)

    row_indices = np.where(rows_with_pixels)[0]
    rmin, rmax = int(row_indices[0]), int(row_indices[-1])

    # Width: maximum horizontal span across all rows
    max_width_px = 0
    for r in range(rmin, rmax + 1):
        row = mask.mask[r]
        if not row.any():
            continue
        col_idx = np.where(row)[0]
        span = int(col_idx[-1]) - int(col_idx[0])
        if span > max_width_px:
            max_width_px = span

    length_px = rmax - rmin

    return FingerMeasurement(
        finger=mask.finger,
        width_mm=round(max_width_px / px_per_mm, 2),
        length_mm=round(length_px / px_per_mm, 2),
        confidence=mask.confidence,
    )


def measure_all_nails(
    masks: List[NailMask], px_per_mm: float
) -> Dict[str, FingerMeasurement]:
    """Return a dict mapping finger name → FingerMeasurement."""
    return {mask.finger: measure_nail(mask, px_per_mm) for mask in masks}
