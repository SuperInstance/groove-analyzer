#!/usr/bin/env python3
"""Analyze a single MIDI file and print a deadband-groove report.

Usage:
    python3 examples/analyze_single.py [midi_file]

Defaults to examples/funk_groove.mid if no path is given.
"""

from __future__ import annotations

import sys
from pathlib import Path

from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import fit_deadband, prove_groove_is_deadband


def main() -> int:
    # Resolve MIDI file path
    if len(sys.argv) > 1:
        midi_path = Path(sys.argv[1])
    else:
        midi_path = Path(__file__).parent / "funk_groove.mid"

    if not midi_path.exists():
        print(f"Error: MIDI file not found: {midi_path}", file=sys.stderr)
        return 1

    print(f"Analyzing: {midi_path}\n")

    # Extract microtiming
    timing = extract_microtiming(midi_path, grid_division=16)

    # Deadband fit
    fit = fit_deadband(timing)
    proof = prove_groove_is_deadband(timing)

    # Print report
    print("─" * 50)
    print("DEADBAND-GROOVE ANALYSIS REPORT")
    print("─" * 50)
    print(f"  BPM:              {timing.bpm:.1f}")
    print(f"  Total onsets:     {sum(len(t.onsets) for t in timing.tracks)}")
    print(f"  Tracks:           {len(timing.tracks)}")
    print()
    print("  Track breakdown:")
    for t in timing.tracks:
        print(f"    {t.track_name:12s}  onsets={len(t.onsets):3d}  "
              f"avg={t.avg_offset_ms:+.2f}ms  std={t.std_offset_ms:.2f}ms  "
              f"pocket={t.pocket_pct:.0f}%")
    print()
    print("  Deadband fit:")
    print(f"    ε (deadband)    {fit.epsilon_ms:.2f} ms")
    print(f"    δ (anomaly)     {fit.delta_ms:.2f} ms")
    print(f"    Coverage        {fit.coverage*100:.1f}%")
    print(f"    Anomaly rate    {fit.anomaly_rate*100:.1f}%")
    print(f"    Confidence      {fit.confidence:.3f}")
    print(f"    Genre match     {fit.genre_match or 'unknown'}")
    print()
    print("  Proof (groove = deadband):")
    print(f"    Coverage          {proof['coverage']:.3f}")
    print(f"    Variance collapse {proof['variance_collapse']:.3f}")
    print(f"    Genre coherence   {proof.get('genre_coherence', 0.0):.3f}")
    print("─" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
