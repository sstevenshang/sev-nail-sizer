"""MediaPipe Hands — landmark detection and finger-width estimation.

Uses the MediaPipe Tasks API (mediapipe.tasks.python.vision.HandLandmarker).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

FINGER_NAMES: List[str] = ["thumb", "index", "middle", "ring", "pinky"]
FINGERTIP_INDICES: List[int] = [4, 8, 12, 16, 20]
DIP_INDICES: List[int] = [3, 7, 11, 15, 19]  # distal interphalangeal joints

# Default model path (relative to cv/ directory)
_DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "models", "hand_landmarker.task"
)


@dataclass
class HandResult:
    landmarks: List[Tuple[int, int]]                # 21 (x, y) pixel coordinates
    handedness: str                                  # "left" | "right"
    fingertip_positions: Dict[str, Tuple[int, int]]  # finger → tip pixel
    finger_widths_px: Dict[str, float]               # finger → estimated width in px


def detect_hand(
    image: np.ndarray,
    hands_model: Any = None,
    model_path: Optional[str] = None,
) -> Optional[HandResult]:
    """
    Run MediaPipe HandLandmarker on *image* (BGR).

    If *hands_model* is provided, it should be a HandLandmarker instance
    (or a mock that returns a compatible result).

    Returns HandResult or None if no hand is found.
    """
    try:
        import mediapipe as mp
        from mediapipe.tasks.python.vision.hand_landmarker import (
            HandLandmarker,
            HandLandmarkerOptions,
        )
        from mediapipe.tasks.python.core.base_options import BaseOptions
    except ImportError:
        return None

    h, w = image.shape[:2]
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # Convert to mediapipe Image
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    if hands_model is None:
        mpath = model_path or _DEFAULT_MODEL_PATH
        if not os.path.isfile(mpath):
            return None
        opts = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=mpath),
            num_hands=1,
            min_hand_detection_confidence=0.5,
        )
        hands_model = HandLandmarker.create_from_options(opts)
        try:
            return _process_result(hands_model.detect(mp_image), h, w)
        finally:
            hands_model.close()
    else:
        # Injected model — could be a HandLandmarker or mock
        result = hands_model.detect(mp_image)
        return _process_result(result, h, w)


def _process_result(results: Any, h: int, w: int) -> Optional[HandResult]:
    """Convert HandLandmarkerResult to HandResult."""
    if not results.hand_landmarks:
        return None

    lm_list = results.hand_landmarks[0]
    handedness_label = results.handedness[0][0].category_name.lower()

    pixel_landmarks: List[Tuple[int, int]] = [
        (int(lm.x * w), int(lm.y * h)) for lm in lm_list
    ]

    fingertip_positions = {
        name: pixel_landmarks[idx]
        for name, idx in zip(FINGER_NAMES, FINGERTIP_INDICES)
    }

    finger_widths_px = _estimate_finger_widths(pixel_landmarks)

    return HandResult(
        landmarks=pixel_landmarks,
        handedness=handedness_label,
        fingertip_positions=fingertip_positions,
        finger_widths_px=finger_widths_px,
    )


def classify_photo_type(hand_result: "HandResult") -> str:
    """Classify whether a photo shows the thumb only or 4 fingers (index–pinky).

    Heuristic:
    - The four-finger shot has index/middle/ring/pinky clustered close together,
      while the thumb is far away.
    - The thumb-only shot has the thumb at a meaningful position while the other
      tips are either at (0,0) or squeezed into a tight cluster close to the wrist.

    Returns "thumb" | "four_finger" | "unknown".
    """
    tips = hand_result.fingertip_positions
    four_names = ["index", "middle", "ring", "pinky"]

    thumb_pos = np.array(tips.get("thumb", (0, 0)), dtype=float)
    four_positions = [np.array(tips.get(n, (0, 0)), dtype=float) for n in four_names]

    # Count how many of the four fingertips are at (0, 0) (sentinel "not present")
    four_at_origin = sum(1 for p in four_positions if p[0] == 0 and p[1] == 0)
    thumb_at_origin = (thumb_pos[0] == 0 and thumb_pos[1] == 0)

    # If all 5 fingertips are at real (non-origin) positions → cannot distinguish,
    # treat as a full 5-finger shot (caller will use all fingers)
    if not thumb_at_origin and four_at_origin == 0:
        return "unknown"

    # If 3+ of the four fingers are at origin but thumb is present → thumb shot
    if four_at_origin >= 3 and not thumb_at_origin:
        return "thumb"

    # If thumb is at origin but four fingers present → four_finger shot
    if thumb_at_origin and four_at_origin < 4:
        return "four_finger"

    # If only thumb seems to have a reasonable width and others don't
    thumb_width = hand_result.finger_widths_px.get("thumb", 0.0)
    four_widths = [hand_result.finger_widths_px.get(n, 0.0) for n in four_names]
    avg_four_width = sum(four_widths) / len(four_widths) if four_widths else 0.0
    if thumb_width > 10 and avg_four_width < 5:
        return "thumb"

    return "unknown"


def _estimate_finger_widths(
    landmarks: List[Tuple[int, int]],
) -> Dict[str, float]:
    """
    Approximate finger widths at the DIP level.

    Each finger's width ≈ 60% of the average distance to its neighbouring
    DIP joints — a rough but reasonable heuristic when no depth data is
    available.
    """
    dip_points = [landmarks[i] for i in DIP_INDICES]
    widths: Dict[str, float] = {}

    for i, name in enumerate(FINGER_NAMES):
        neighbours = []
        if i > 0:
            neighbours.append(dip_points[i - 1])
        if i < len(FINGER_NAMES) - 1:
            neighbours.append(dip_points[i + 1])

        if neighbours:
            avg_dist = float(
                np.mean(
                    [
                        np.linalg.norm(
                            np.array(dip_points[i]) - np.array(n)
                        )
                        for n in neighbours
                    ]
                )
            )
            widths[name] = avg_dist * 0.6
        else:
            widths[name] = 30.0

    return widths
