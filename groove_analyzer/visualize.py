"""Visualise microtiming data as a deadband funnel.

X axis: time (beats)
Y axis: microtiming offset (ms)
Shaded region: deadband ε(t)
Points: actual onsets (colour = instrument)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np

from .deadband_groove import EnsembleFunnel, build_funnel, fit_deadband
from .microtiming import GrooveTiming, TrackTiming


def plot_deadband_funnel(
    timing: GrooveTiming,
    funnel: Optional[EnsembleFunnel] = None,
    title: str = "Groove = Deadband Funnel",
    save_path: Optional[Path | str] = None,
    figsize: tuple[int, int] = (12, 6),
) -> plt.Figure:
    """Plot the microtiming data with the deadband funnel overlay.

    Parameters
    ----------
    timing : GrooveTiming
    funnel : EnsembleFunnel, optional
        Pre-built funnel.  If None, one is computed automatically.
    title : str
    save_path : Path or str, optional
    figsize : tuple

    Returns
    -------
    matplotlib.figure.Figure
    """
    if funnel is None:
        funnel = build_funnel(timing)

    fig, ax = plt.subplots(figsize=figsize)

    # Colour map per track
    cmap = plt.colormaps["tab10"]
    colours = {t.track_name: cmap(i % 10) for i, t in enumerate(timing.tracks)}

    # Plot each onset
    for track in timing.tracks:
        beats = [o.beat for o in track.onsets]
        devs = [o.deviation_ms for o in track.onsets]
        ax.scatter(beats, devs, label=track.track_name,
                   color=colours[track.track_name], alpha=0.8, s=40, edgecolors="k", linewidths=0.3)

    # Plot deadband funnel envelope
    if timing.tracks:
        all_beats = [o.beat for t in timing.tracks for o in t.onsets]
        max_beat = max(all_beats) if all_beats else 16.0
    else:
        max_beat = 16.0

    beat_grid = np.linspace(0, max_beat, 500)
    epsilon_curve = funnel.deadband_ms * np.exp(-funnel.decay_rate * beat_grid)
    delta_curve = funnel.delta_ms * np.exp(-funnel.decay_rate * beat_grid)

    ax.fill_between(beat_grid, -epsilon_curve, epsilon_curve,
                    color="green", alpha=0.15, label=f"Deadband ε = {funnel.deadband_ms:.1f} ms")
    ax.fill_between(beat_grid, epsilon_curve, delta_curve,
                    color="orange", alpha=0.10)
    ax.fill_between(beat_grid, -delta_curve, -epsilon_curve,
                    color="orange", alpha=0.10, label=f"Approach zone δ = {funnel.delta_ms:.1f} ms")
    ax.plot(beat_grid, epsilon_curve, "g--", linewidth=1.0)
    ax.plot(beat_grid, -epsilon_curve, "g--", linewidth=1.0)
    ax.plot(beat_grid, delta_curve, "r--", linewidth=1.0, alpha=0.5)
    ax.plot(beat_grid, -delta_curve, "r--", linewidth=1.0, alpha=0.5)

    ax.axhline(0, color="black", linewidth=0.8, linestyle="-", alpha=0.4)
    ax.set_xlabel("Time (beats)", fontsize=12)
    ax.set_ylabel("Microtiming offset (ms)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlim(0, max_beat)
    # Y limit: at least ± max delta, or ± 60 ms
    ylim = max(funnel.delta_ms * 1.2, 60.0)
    ax.set_ylim(-ylim, ylim)
    ax.grid(True, alpha=0.3)

    # Annotation
    fit = fit_deadband(timing)
    text = (
        f"ε = {fit.epsilon_ms:.1f} ms\n"
        f"δ = {fit.delta_ms:.1f} ms\n"
        f"Coverage = {fit.coverage*100:.0f}%\n"
        f"Genre match: {fit.genre_match or 'unknown'}"
    )
    ax.text(0.02, 0.98, text, transform=ax.transAxes,
            fontsize=10, verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    fig.tight_layout()

    if save_path is not None:
        fig.savefig(str(save_path), dpi=150)

    return fig


def plot_groove_comparison(
    timings: Dict[str, GrooveTiming],
    save_path: Optional[Path | str] = None,
    figsize: tuple[int, int] = (14, 8),
) -> plt.Figure:
    """Plot a grid of deadband funnel plots for multiple files / genres."""
    n = len(timings)
    cols = min(3, n)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=figsize, squeeze=False)

    for idx, (label, timing) in enumerate(timings.items()):
        ax = axes[idx // cols][idx % cols]
        funnel = build_funnel(timing)

        cmap = plt.colormaps["tab10"]
        colours = {t.track_name: cmap(i % 10) for i, t in enumerate(timing.tracks)}

        for track in timing.tracks:
            beats = [o.beat for o in track.onsets]
            devs = [o.deviation_ms for o in track.onsets]
            ax.scatter(beats, devs, label=track.track_name,
                       color=colours[track.track_name], alpha=0.7, s=30)

        max_beat = max((o.beat for t in timing.tracks for o in t.onsets), default=16.0)
        beat_grid = np.linspace(0, max_beat, 300)
        eps_curve = funnel.deadband_ms * np.exp(-funnel.decay_rate * beat_grid)
        del_curve = funnel.delta_ms * np.exp(-funnel.decay_rate * beat_grid)
        ax.fill_between(beat_grid, -eps_curve, eps_curve, color="green", alpha=0.15)
        ax.plot(beat_grid, eps_curve, "g--", linewidth=0.8)
        ax.plot(beat_grid, -eps_curve, "g--", linewidth=0.8)
        ax.plot(beat_grid, del_curve, "r--", linewidth=0.8, alpha=0.4)
        ax.plot(beat_grid, -del_curve, "r--", linewidth=0.8, alpha=0.4)
        ax.axhline(0, color="black", linewidth=0.6, alpha=0.4)

        ax.set_title(label, fontsize=11, fontweight="bold")
        ax.set_xlabel("Beats")
        ax.set_ylabel("Offset (ms)")
        ax.set_xlim(0, max_beat)
        ylim = max(funnel.delta_ms * 1.2, 50.0)
        ax.set_ylim(-ylim, ylim)
        ax.grid(True, alpha=0.3)

        fit = fit_deadband(timing)
        ax.text(0.98, 0.98, f"ε={fit.epsilon_ms:.1f}ms\n{fit.genre_match}",
                transform=ax.transAxes, fontsize=9, verticalalignment="top",
                horizontalalignment="right",
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    # Hide unused subplots
    for idx in range(n, rows * cols):
        axes[idx // cols][idx % cols].axis("off")

    fig.suptitle("Groove = Deadband Funnel — Genre Comparison", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    if save_path is not None:
        fig.savefig(str(save_path), dpi=150)

    return fig
