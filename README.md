# groove-analyzer

🥁 Microtiming analysis proving groove = deadband funnel — genre-specific ε profiles, visualization, synthetic groove generation.

## What It Does

Extracts microtiming deviations from MIDI files, fits a deadband ε that contains the groove pocket, and visualizes the result as a narrowing funnel. Also generates synthetic genre-specific grooves with characteristic timing profiles.

## Why It Exists

Every genre has a characteristic timing tolerance (EDM ≈ 3ms, Jazz ≈ 40ms). The onsets cluster inside this ε with high coverage, and variance collapses when conditioned on the pocket. This library proves that **the groove pocket IS the deadband ε** from control systems theory. The narrowing funnel over time models how an ensemble locks in.

The math: microtiming offsets are local phase deviations from a shared metronome lattice. When all deviations lie within ε, the ensemble is "in the pocket" (FunnelPhase.NARROWING). Exceeding δ breaks the groove (FunnelPhase.ANOMALY).

## Quick Start

```bash
pip install -e .
```

```python
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import fit_deadband, prove_groove_is_deadband

# Analyze any MIDI file
timing = extract_microtiming("my_performance.mid", grid_division=16)

# Fit the deadband
fit = fit_deadband(timing)
print(f"ε = {fit.epsilon_ms:.1f} ms, coverage = {fit.coverage*100:.0f}%")
print(f"Genre match: {fit.genre_match}")

# Quantitative proof
proof = prove_groove_is_deadband(timing)
print(proof)
# {'coverage': 0.92, 'variance_collapse': 0.87, 'genre_coherence': 0.95, ...}

# Visualize
from groove_analyzer.visualize import plot_deadband_funnel
fig = plot_deadband_funnel(timing, save_path="funnel.png")
```

## API Overview

### Microtiming Extraction (`groove_analyzer.microtiming`)

```python
from groove_analyzer.microtiming import extract_microtiming, GrooveTiming, TrackTiming, OnsetEvent

timing = extract_microtiming(
    "drums.mid",
    grid_division=16,    # 16th-note grid
    pocket_ms=None,      # auto-computed (1.5 × MAD)
)
```

| Function | Returns |
|----------|---------|
| `extract_microtiming(path, grid_division, pocket_ms)` | `GrooveTiming` |

**Data structures:**

| Class | Key fields |
|-------|------------|
| `GrooveTiming` | `bpm`, `ticks_per_beat`, `grid_division`, `tracks`, `global_avg_offset_ms`, `global_std_offset_ms`, `global_swing_factor` |
| `TrackTiming` | `track_name`, `onsets`, `avg_offset_ms`, `std_offset_ms`, `swing_factor`, `pocket_pct`, `ahead_pct`, `behind_pct` |
| `OnsetEvent` | `time_sec`, `beat`, `pitch`, `velocity`, `deviation_ms`, `timing_class` (AHEAD/BEHIND/POCKET) |
| `TimingClass` | Enum: `AHEAD`, `BEHIND`, `POCKET` |

### Deadband Fitting (`groove_analyzer.deadband_groove`)

```python
from groove_analyzer.deadband_groove import fit_deadband, build_funnel, prove_groove_is_deadband

fit = fit_deadband(timing, coverage_target=0.90, delta_mult=2.5)
# DeadbandFit(epsilon_ms=15.2, delta_ms=38.0, coverage=0.91, ...)

funnel = build_funnel(timing, decay_rate=0.05)
# EnsembleFunnel(deadband_ms=15.2, delta_ms=38.0, ...)

proof = prove_groove_is_deadband(timing)
# {'coverage': 0.91, 'variance_collapse': 0.85, 'genre_coherence': 0.93}
```

| Function | Returns |
|----------|---------|
| `fit_deadband(timing, coverage_target, delta_mult)` | `DeadbandFit` |
| `build_funnel(timing, epsilon_0, decay_rate, delta_mult)` | `EnsembleFunnel` |
| `prove_groove_is_deadband(timing)` | `Dict[str, float]` — coverage, variance_collapse, genre_coherence |

| Class | Key fields |
|-------|------------|
| `DeadbandFit` | `epsilon_ms`, `delta_ms`, `coverage`, `anomaly_rate`, `genre_match`, `confidence` |
| `EnsembleFunnel` | `deadband_ms`, `delta_ms`, `decay_rate`, `player_funnels` |
| `PlayerState` | `beat`, `deviation_ms`, `phase` (narrowing/approach/anomaly), `epsilon_at_beat` |

### Genre Profiles (`groove_analyzer.genres`)

```python
from groove_analyzer.genres import synthesize_groove, generate_all_genre_examples, GENRE_PROFILES

# Generate synthetic groove
mid = synthesize_groove("Funk", bars=4, seed=42, output_path="funk.mid")

# All 5 genres
paths = generate_all_genre_examples("examples/", bars=8, seed=42)
```

| Function | Returns |
|----------|---------|
| `synthesize_groove(genre, bars, parts, seed, output_path)` | `mido.MidiFile` |
| `generate_all_genre_examples(output_dir, bars, seed)` | `List[Path]` |

| Genre | ε (ms) | Swing | BPM | Pocket description |
|-------|--------|-------|-----|-------------------|
| EDM | 3 | 0.0 | 128 | Nearly quantized |
| Funk | 15 | 0.15 | 105 | Tight pocket, low swing |
| Hip-hop | 20 | 0.35 | 90 | Medium pocket, laid-back |
| Latin | 30 | 0.50 | 110 | Polyrhythmic offsets |
| Jazz | 40 | 0.75 | 120 | Wide pocket, high swing |

### Visualization (`groove_analyzer.visualize`)

```python
from groove_analyzer.visualize import plot_deadband_funnel, plot_groove_comparison

fig = plot_deadband_funnel(timing, title="Funk Funnel", save_path="funk.png")
fig = plot_groove_comparison(timings_dict, save_path="comparison.png")
```

| Function | Returns |
|----------|---------|
| `plot_deadband_funnel(timing, funnel, title, save_path, figsize)` | `plt.Figure` |
| `plot_groove_comparison(timings, save_path, figsize)` | `plt.Figure` |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   groove-analyzer                    │
│                                                     │
│  microtiming.py                                     │
│  ┌────────────────────────────────┐                 │
│  │ extract_microtiming(path)      │                 │
│  │   → GrooveTiming               │                 │
│  │     .tracks → TrackTiming[]    │                 │
│  │       .onsets → OnsetEvent[]   │                 │
│  └──────────────┬─────────────────┘                 │
│                 │                                    │
│                 ▼                                    │
│  deadband_groove.py                                  │
│  ┌────────────────────────────────┐                 │
│  │ fit_deadband(timing)           │                 │
│  │   → DeadbandFit                │                 │
│  │ build_funnel(timing)           │                 │
│  │   → EnsembleFunnel             │                 │
│  │ prove_groove_is_deadband()     │                 │
│  │   → {coverage, var_collapse,   │                 │
│  │      genre_coherence}          │                 │
│  └──────────────┬─────────────────┘                 │
│                 │                                    │
│       ┌─────────┴──────────┐                        │
│       ▼                    ▼                        │
│  genres.py            visualize.py                  │
│  ┌───────────────┐    ┌──────────────────┐         │
│  │ synthesize_   │    │ plot_deadband_   │         │
│  │ groove()      │    │ funnel()         │         │
│  │               │    │ plot_groove_     │         │
│  │ GENRE_PROFILES│    │ comparison()     │         │
│  └───────────────┘    └──────────────────┘         │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Dependencies: mido, numpy, matplotlib              │
└─────────────────────────────────────────────────────┘
```

Data flow: `MIDI file → extract_microtiming → fit_deadband → build_funnel → plot`

## Documentation

- [User Guide](docs/USER-GUIDE.md) — Complete usage documentation
- [Developer Guide](docs/DEVELOPER-GUIDE.md) — Contributing and internals
- [Examples](examples/) — Working code examples
- [Report](docs/report/GROOVE_REPORT.md) — Genre groove analysis report

## Ecosystem

- **[constraint-theory-core](https://github.com/SuperInstance/constraint-theory-core)** — Deadband theory, constraint checking
- **[flux-tensor-midi](https://github.com/SuperInstance/flux-tensor-midi)** — Tensor-MIDI event encoding
- **[counterpoint-engine](https://github.com/SuperInstance/counterpoint-engine)** — Species counterpoint as constraint satisfaction

## Requirements

- Python ≥ 3.9
- `mido >= 1.3`
- `numpy >= 1.24`
- `matplotlib >= 3.8` (for visualization)

## Installation

```bash
pip install groove-analyzer
```

Or install from source:

```bash
git clone https://github.com/SuperInstance/groove-analyzer.git
cd groove-analyzer
pip install -e ".[dev]"
pytest  # 11/11 pass ✅
```

## Status

![Tests](https://img.shields.io/badge/tests-11%2F11-passing-brightgreen) ![Version](https://img.shields.io/badge/version-0.1.0-blue) ![License](https://img.shields.io/badge/license-Apache%202.0-green)

## License

Apache 2.0
