#!/usr/bin/env python3
"""Generate all 5 genres, analyze each, and show a deadband comparison table.

Usage:
    python3 examples/compare_genres.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from groove_analyzer.genres import synthesize_groove, GENRE_PROFILES
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import fit_deadband


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="groove_compare_") as tmp:
        tmp_path = Path(tmp)

        print("Generating and analyzing all 5 genre grooves...\n")

        rows = []
        for genre in GENRE_PROFILES:
            midi_path = tmp_path / f"{genre.lower().replace('-', '_')}_groove.mid"
            synthesize_groove(genre, bars=4, seed=42, output_path=midi_path)

            timing = extract_microtiming(midi_path, grid_division=16)
            fit = fit_deadband(timing)
            total_onsets = sum(len(t.onsets) for t in timing.tracks)

            rows.append({
                "genre": genre,
                "bpm": timing.bpm,
                "onsets": total_onsets,
                "epsilon_ms": fit.epsilon_ms,
                "delta_ms": fit.delta_ms,
                "coverage": fit.coverage,
                "anomaly_rate": fit.anomaly_rate,
                "confidence": fit.confidence,
                "genre_match": fit.genre_match or "unknown",
            })

        # Print comparison table
        header = (
            f"{'Genre':<10} {'BPM':>5} {'Onsets':>6} "
            f"{'ε (ms)':>8} {'δ (ms)':>8} {'Coverage':>8} "
            f"{'Anomaly%':>8} {'Confidence':>10} {'Match':>8}"
        )
        print("─" * len(header))
        print(header)
        print("─" * len(header))
        for r in rows:
            print(
                f"{r['genre']:<10} {r['bpm']:>5.0f} {r['onsets']:>6d} "
                f"{r['epsilon_ms']:>8.2f} {r['delta_ms']:>8.2f} "
                f"{r['coverage']*100:>7.1f}% {r['anomaly_rate']*100:>7.1f}% "
                f"{r['confidence']:>10.3f} {r['genre_match']:>8}"
            )
        print("─" * len(header))

        # Summary insight
        print("\nInsight: EDM has the tightest deadband (≈3 ms), Jazz the widest (≈40 ms).")
        print("          Each genre’s fitted ε clusters near its profile target.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
