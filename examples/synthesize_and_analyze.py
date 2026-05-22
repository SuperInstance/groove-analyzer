#!/usr/bin/env python3
"""Synthesize a groove, analyze it, and assert coverage > 0.85.

Usage:
    python3 examples/synthesize_and_analyze.py [genre]

Defaults to Funk. Valid genres: Jazz, Funk, Hip-hop, EDM, Latin.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from groove_analyzer.genres import synthesize_groove, GENRE_PROFILES
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import fit_deadband, prove_groove_is_deadband


def main() -> int:
    genre = sys.argv[1] if len(sys.argv) > 1 else "Funk"
    if genre not in GENRE_PROFILES:
        print(f"Error: unknown genre '{genre}'. Choose from: {', '.join(GENRE_PROFILES)}",
              file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="groove_synth_") as tmp:
        midi_path = Path(tmp) / f"{genre.lower().replace('-', '_')}_groove.mid"

        print(f"Synthesizing {genre} groove...")
        synthesize_groove(genre, bars=4, seed=42, output_path=midi_path)

        print(f"Analyzing:  {midi_path}")
        timing = extract_microtiming(midi_path, grid_division=16)
        fit = fit_deadband(timing)
        proof = prove_groove_is_deadband(timing)

        print()
        print("Results:")
        print(f"  ε (deadband)  = {fit.epsilon_ms:.2f} ms")
        print(f"  Coverage      = {fit.coverage:.3f}")
        print(f"  Variance col. = {proof['variance_collapse']:.3f}")
        print(f"  Genre match   = {fit.genre_match}")
        print()

        # The core claim: coverage must exceed 0.85
        coverage = proof["coverage"]
        if coverage > 0.85:
            print(f"✅ PASS: coverage {coverage:.3f} > 0.85")
            return 0
        else:
            print(f"❌ FAIL: coverage {coverage:.3f} ≤ 0.85", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
