"""Tests for visualization (smoke tests)."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

from groove_analyzer.genres import synthesize_groove
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.visualize import plot_deadband_funnel, plot_groove_comparison


def test_plot_funnel(tmp_path: Path):
    path = tmp_path / "funk.mid"
    synthesize_groove("Funk", bars=2, seed=42, output_path=path)
    gt = extract_microtiming(path)
    fig = plot_deadband_funnel(gt, save_path=tmp_path / "funk.png")
    assert fig is not None
    assert (tmp_path / "funk.png").exists()


def test_plot_comparison(tmp_path: Path):
    timings = {}
    for genre in ("EDM", "Jazz", "Funk"):
        path = tmp_path / f"{genre}.mid"
        synthesize_groove(genre, bars=2, seed=42, output_path=path)
        timings[genre] = extract_microtiming(path)
    fig = plot_groove_comparison(timings, save_path=tmp_path / "compare.png")
    assert fig is not None
    assert (tmp_path / "compare.png").exists()
