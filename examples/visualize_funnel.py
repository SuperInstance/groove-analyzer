#!/usr/bin/env python3
"""Load a MIDI file, plot its deadband funnel, and save a PNG.

Usage:
    python3 examples/visualize_funnel.py [midi_file] [output_png]

Defaults:
    midi_file  → examples/jazz_groove.mid
    output_png → examples/funnel_plot.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend

from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.visualize import plot_deadband_funnel


def main() -> int:
    midi_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "jazz_groove.mid"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "funnel_plot.png"

    if not midi_path.exists():
        print(f"Error: MIDI file not found: {midi_path}", file=sys.stderr)
        return 1

    print(f"Loading:   {midi_path}")
    timing = extract_microtiming(midi_path, grid_division=16)

    genre = midi_path.stem.replace("_groove", "").replace("_", " ").title()
    title = f"{genre} — Groove = Deadband Funnel"

    fig = plot_deadband_funnel(timing, title=title, save_path=out_path)
    fig.clear()

    print(f"Saved PNG: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
