# Groove Analyzer — Developer Guide

## Architecture

```
groove_analyzer/
├── __init__.py            # Version + package marker
├── microtiming.py         # MIDI → timing data extraction
├── deadband_groove.py     # Deadband fitting + funnel building
├── genres.py              # Genre profiles + synthetic MIDI generation
├── visualize.py           # Matplotlib funnel/comparison plots
tests/
├── test_microtiming.py    # Extraction + genre synthesis tests
├── test_visualize.py      # Plot smoke tests
analyze_grooves.py         # CLI report generator
```

### Module Diagram

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│  genres.py   │────▶│  microtiming.py │────▶│deadband_     │
│ (synth MIDI) │     │ (extract timing)│     │  groove.py   │
└──────────────┘     └────────┬────────┘     │(fit ε, build │
                              │              │ funnel, prove)│
                              │              └──────┬───────┘
                     ┌────────▼────────┐            │
                     │  visualize.py   │◀───────────┘
                     │ (matplotlib)    │
                     └─────────────────┘
```

### Data Flow

1. MIDI file → `extract_microtiming()` → `GrooveTiming` (per-track onsets with deviations)
2. `GrooveTiming` → `fit_deadband()` → `DeadbandFit` (ε, δ, coverage, genre match)
3. `GrooveTiming` → `build_funnel()` → `EnsembleFunnel` (per-player phase trajectory)
4. Any of the above → `visualize.py` → matplotlib figures

## Extending

### Adding a New Genre Profile

Add to `GENRE_PROFILES` in `genres.py`:

```python
GENRE_PROFILES["Rock"] = GenreProfile(
    name="Rock",
    epsilon_ms=12.0,
    epsilon_range=(8.0, 18.0),
    swing_factor=0.05,
    pocket_description="driving, slightly ahead",
    bpm=130.0,
    velocity_mean=95,
    velocity_std=8,
    distribution="gaussian",
    ahead_bias=-3.0,  # rock drummers push
)
```

The genre will automatically be available in `synthesize_groove("Rock", ...)` and `generate_all_genre_examples()`.

### Adding a New Timing Feature

Add to `microtiming.py` as a function that takes `GrooveTiming`:

```python
def compute_groove_entropy(timing: GrooveTiming) -> float:
    """Measure the information-theoretic entropy of timing deviations."""
    import math
    devs = [o.deviation_ms for t in timing.tracks for o in t.onsets]
    if not devs:
        return 0.0
    # Bin into histogram
    n_bins = 20
    counts = [0] * n_bins
    for d in devs:
        idx = min(n_bins - 1, max(0, int((d + 50) / 100 * n_bins)))
        counts[idx] += 1
    total = sum(counts)
    entropy = -sum((c/total) * math.log2(c/total) for c in counts if c > 0)
    return entropy
```

### Adding a New Deadband Model

Extend `deadband_groove.py`:

```python
def fit_adaptive_deadband(timing: GrooveTiming) -> AdaptiveDeadbandFit:
    """Fit a deadband that varies over time (non-stationary ε)."""
    # Segment the timing data and fit ε per segment
    ...
```

### Adding a New Visualization

Follow the pattern in `visualize.py`:

```python
def plot_offset_histogram(
    timing: GrooveTiming,
    save_path: Path | str | None = None,
) -> plt.Figure:
    fig, ax = plt.subplots()
    for track in timing.tracks:
        devs = [o.deviation_ms for o in track.onsets]
        ax.hist(devs, bins=30, alpha=0.5, label=track.track_name)
    ax.set_xlabel("Offset (ms)")
    ax.set_ylabel("Count")
    ax.legend()
    if save_path:
        fig.savefig(str(save_path), dpi=150)
    return fig
```

## Testing

### Running Tests

```bash
pytest                          # all tests
pytest tests/test_microtiming.py  # timing + deadband + genre tests
pytest tests/test_visualize.py    # plot smoke tests
pytest -v                        # verbose
pytest --cov=groove_analyzer     # coverage
```

### Test Structure

Tests generate synthetic MIDI via `synthesize_groove()`, extract timing, and verify properties:

```python
def test_jazz_wider_than_edm(tmp_path):
    """Jazz deadband should be wider than EDM."""
    edm = synthesize_groove("EDM", bars=4, seed=1, output_path=tmp_path / "e.mid")
    jazz = synthesize_groove("Jazz", bars=4, seed=1, output_path=tmp_path / "j.mid")
    fit_edm = fit_deadband(extract_microtiming(tmp_path / "e.mid"))
    fit_jazz = fit_deadband(extract_microtiming(tmp_path / "j.mid"))
    assert fit_jazz.epsilon_ms > fit_edm.epsilon_ms
```

### Adding Tests

1. Use `synthesize_groove()` to create test fixtures (no external MIDI files needed)
2. Test invariants, not exact values (timing depends on RNG)
3. Use `tmp_path` fixture for file output

## Contributing

1. Fork, branch, implement, test, PR
2. All new features need tests
3. Visualization functions must work with `matplotlib.use("Agg")` (headless)
4. Follow existing naming: `snake_case` for functions, `PascalCase` for classes

### Code Style

- Python 3.9+ type hints
- Dataclasses for structured return types
- `from __future__ import annotations` in all modules
- Docstrings with Parameters/Returns on all public functions
- `mido` for MIDI I/O, `numpy` for numerical work, `matplotlib` for plots

### Build System

`pyproject.toml` with `setuptools`. Dependencies: `mido>=1.3`, `numpy>=1.24`, `matplotlib>=3.8`.

```bash
pip install -e .           # install in development
pip install -e ".[dev]"    # with pytest
```
