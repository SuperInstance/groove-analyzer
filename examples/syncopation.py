#!/usr/bin/env python3
"""
syncopation.py — Analyze syncopation and microtiming patterns.

Demonstrates:
- Generating grooves with different ahead/behind biases
- Comparing timing classifications (ahead, behind, pocket)
- Showing how swing factor affects microtiming
- Examining individual onset deviations

Run:  python3 examples/syncopation.py
"""

import tempfile
from pathlib import Path

from groove_analyzer import (
    synthesize_groove,
    extract_microtiming,
    fit_deadband,
    TimingClass,
)

genres_to_test = ["Jazz", "Funk", "Hip-hop", "EDM", "Latin"]

print("SYNCOPATION & MICROTIMING ANALYSIS")
print("=" * 60)

for genre in genres_to_test:
    print()
    print(f"--- {genre} ---")

    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
        mid_path = Path(tmp.name)

    mid = synthesize_groove(genre, bars=4, seed=42, output_path=mid_path)
    timing = extract_microtiming(mid_path, grid_division=4)
    fit = fit_deadband(timing)

    print(f"  BPM: {timing.bpm:.0f} | Swing: {timing.global_swing_factor:.2f}")
    print(f"  Deadband e: {fit.epsilon_ms:.1f}ms | Coverage: {fit.coverage:.0%} | Confidence: {fit.confidence:.2f}")
    print()

    # Show per-track timing breakdown
    for track in timing.tracks:
        ahead = sum(1 for o in track.onsets if o.timing_class == TimingClass.AHEAD)
        behind = sum(1 for o in track.onsets if o.timing_class == TimingClass.BEHIND)
        pocket = sum(1 for o in track.onsets if o.timing_class == TimingClass.POCKET)
        total = len(track.onsets)

        print(f"  {track.track_name:12s}: avg={track.avg_offset_ms:+6.2f}ms  "
              f"std={track.std_offset_ms:5.2f}ms  "
              f"pocket={pocket}/{total}  ahead={ahead}  behind={behind}")

    mid_path.unlink(missing_ok=True)

print()
print("=" * 60)
print("KEY INSIGHT:")
print("  Jazz has the widest deadband (most 'loose' timing)")
print("  EDM has the narrowest (nearly quantized)")
print("  Hip-hop and Funk lay back (positive avg offset)")
print("  Latin shows polyrhythmic offsets from the grid")
