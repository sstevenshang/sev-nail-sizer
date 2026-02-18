#!/usr/bin/env python3
"""
Test the full CV pipeline on a real image.

Usage:
    .venv/bin/python cv/test_real.py path/to/photo.jpg [--hand left|right] [--mock-seg]

Runs: preprocess → card_detect → hand_detect → nail_segment → measure → curve_adjust → debug_viz
Prints per-finger results and saves a debug image next to the input.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# Ensure pipeline imports work
sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description="Run full nail-sizer CV pipeline on an image")
    parser.add_argument("image", help="Path to input image (JPEG or PNG)")
    parser.add_argument("--hand", choices=["left", "right"], default=None, help="Override hand detection")
    parser.add_argument("--mock-seg", action="store_true", help="Use mock (ellipse) segmentation instead of OpenCV HSV")
    parser.add_argument("--output", "-o", default=None, help="Output debug image path (default: <input>_debug.jpg)")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.is_file():
        print(f"❌ File not found: {image_path}")
        sys.exit(1)

    raw_bytes = image_path.read_bytes()
    print(f"📷 Input: {image_path} ({len(raw_bytes) / 1024:.0f} KB)")

    # ── 1. Preprocess ──────────────────────────────────────────────────────────
    from pipeline.preprocess import preprocess

    t0 = time.time()
    img, quality = preprocess(raw_bytes)
    t_pre = time.time() - t0
    print(f"\n🔧 Preprocess ({t_pre:.2f}s)")
    print(f"   Image: {img.shape[1]}×{img.shape[0]}")
    print(f"   Blur score: {quality.blur_score:.1f} ({'✅ sharp' if quality.is_sharp else '⚠️  blurry'})")
    print(f"   Brightness: {quality.brightness_mean:.1f} ({quality.brightness_level})")

    if not quality.is_sharp:
        print("⚠️  Image may be too blurry for accurate measurements")

    # ── 2. Card detect ─────────────────────────────────────────────────────────
    from pipeline.card_detect import detect_card

    t0 = time.time()
    card_result = detect_card(img)
    t_card = time.time() - t0

    if card_result is None:
        print(f"\n❌ Card not detected ({t_card:.2f}s)")
        print("   Make sure the full credit card is visible in the frame")
        sys.exit(1)

    print(f"\n💳 Card detected ({t_card:.2f}s)")
    print(f"   Scale: {card_result.px_per_mm:.2f} px/mm")
    print(f"   Confidence: {card_result.confidence:.2f}")

    # ── 3. Hand detect ─────────────────────────────────────────────────────────
    from pipeline.hand_detect import detect_hand

    t0 = time.time()
    hand_result = detect_hand(img)
    t_hand = time.time() - t0

    if hand_result is None:
        print(f"\n❌ Hand not detected ({t_hand:.2f}s)")
        print("   Make sure your hand is flat with fingers spread")
        sys.exit(1)

    detected_hand = args.hand or hand_result.handedness
    print(f"\n✋ Hand detected ({t_hand:.2f}s)")
    print(f"   Handedness: {detected_hand}")
    print(f"   Fingertips: {list(hand_result.fingertip_positions.keys())}")

    # ── 4. Nail segment ───────────────────────────────────────────────────────
    from pipeline.nail_segment import segment_nails

    if args.mock_seg:
        os.environ["SEV_MOCK_SEGMENTATION"] = "1"

    t0 = time.time()
    nail_masks = segment_nails(img, hand_result.fingertip_positions, mock=args.mock_seg)
    t_seg = time.time() - t0
    print(f"\n💅 Nail segmentation ({t_seg:.2f}s, {'mock' if args.mock_seg else 'OpenCV HSV'})")
    for m in nail_masks:
        px_count = int(m.mask.sum())
        print(f"   {m.finger}: {px_count} px, conf={m.confidence:.2f}")

    # ── 5. Measure ─────────────────────────────────────────────────────────────
    from pipeline.measure import measure_all_nails
    from pipeline.curve_adjust import adjust_curve

    t0 = time.time()
    raw_measurements = measure_all_nails(nail_masks, card_result.px_per_mm)
    t_meas = time.time() - t0

    print(f"\n📏 Measurements ({t_meas:.2f}s)")
    print(f"   {'Finger':<8} {'Width':>7} {'Length':>7} {'Curved':>7} {'Conf':>6}")
    print(f"   {'─'*8} {'─'*7} {'─'*7} {'─'*7} {'─'*6}")

    finger_names = ["thumb", "index", "middle", "ring", "pinky"]
    warnings = []
    total_conf = 0.0
    n = 0

    for name in finger_names:
        meas = raw_measurements.get(name)
        if meas is None or meas.width_mm == 0:
            print(f"   {name:<8} {'—':>7} {'—':>7} {'—':>7} {'—':>6}")
            warnings.append(f"{name}_not_detected")
            continue

        finger_width_px = hand_result.finger_widths_px.get(name, 0.0)
        curve_adj = adjust_curve(meas, finger_width_px, card_result.px_per_mm)
        total_conf += meas.confidence
        n += 1

        print(f"   {name:<8} {meas.width_mm:>6.1f}m {meas.length_mm:>6.1f}m {curve_adj:>6.1f}m {meas.confidence:>5.2f}")

    if n > 0:
        overall_conf = total_conf / n
        print(f"\n   Overall confidence: {overall_conf:.3f}")
    else:
        print("\n   ⚠️  No nails measured!")

    if warnings:
        print(f"   Warnings: {', '.join(warnings)}")

    # ── 6. Debug viz ───────────────────────────────────────────────────────────
    from pipeline.debug_viz import draw_debug_image

    debug_img = draw_debug_image(
        img,
        card_result=card_result,
        hand_result=hand_result,
        nail_masks=nail_masks,
        measurements=raw_measurements,
    )

    output_path = args.output or str(image_path.with_suffix('')) + '_debug.jpg'
    cv2.imwrite(output_path, debug_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(f"\n🖼️  Debug image saved: {output_path}")

    total_time = t_pre + t_card + t_hand + t_seg + t_meas
    print(f"⏱️  Total pipeline time: {total_time:.2f}s")


if __name__ == "__main__":
    main()
