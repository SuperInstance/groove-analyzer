# groove-analyzer — Developer Guide

## Architecture

### Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `microtiming.py` | MIDI parsing, onset extraction, grid quantization, timing classification |
| `deadband_groove.py` | Deadband fitting, funnel construction, proof metrics. Pure computation. |
| `genres.py` | Genre profiles, synthetic groove generation, MIDI file output |
| `visualize.py` | Matplotlib funnel plots. Depends on all three other modules. |

### Data Flow

```
MIDI file (.mid)
      │
      ▼
┌──────────────────────────┐
│ microtiming.py           │
│                          │
│ _build_tempo_map()       │  Parse tempo events
│ _tick_to_seconds()       │  Convert ticks → seconds
│ _snap_to_grid()          │  Quantize to grid
│ _classify_deviation()    │  Ahead/Behind/Pocket
│ _compute_swing()         │  Swing factor estimation
│                          │
│ extract_microtiming()    │
│   → GrooveTiming         │
│     .tracks → TrackTiming[]│
│       .onsets → OnsetEvent[]│
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ deadband_groove.py       │
│                          │
│ fit_deadband()           │  → DeadbandFit
│   _match_genre()         │  ε → closest genre
│                          │
│ build_funnel()           │  → EnsembleFunnel
│   ε(t) = ε₀·e^(-λt)    │  Exponential decay
│   PlayerState per onset  │  narrowing/approach/anomaly
│                          │
│ prove_groove_is_deadband │  → {coverage, variance_collapse, genre_coherence}
└──────────┬───────────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
┌──────────┐ ┌──────────────┐
│ genres.py│ │ visualize.py │
│          │ │              │
│ synthesize_ │ │ plot_deadband_│
│ groove() │ │ funnel()     │
│          │ │ plot_groove_ │
│ generate_ │ │ comparison() │
│ all_genre│ │              │
│ _examples│ │ Uses matplotlib│
│          │ │ for rendering │
│ GENRE_   │ └──────────────┘
│ PROFILES │
└──────────┘
```

### Key Design Decisions

1. **MIDI as input, not audio.** Microtiming extraction from MIDI is deterministic and doesn't require onset detection. Audio support could be added as a separate front-end.

2. **Grid-based quantization.** Onsets are snapped to a regular grid (16th notes by default). The deviation from the grid is the microtiming offset. This is standard in musicology.

3. **Deadband from coverage, not from theory.** We fit ε to achieve a target coverage (default 90%) rather than imposing a theoretical value. This is data-driven.

4. **Exponential funnel decay.** The narrowing funnel models how ensembles converge over time. The decay rate λ controls how fast.

5. **Genre profiles as references, not classifiers.** The genre match is the nearest profile by ε. It's a descriptive statistic, not a machine learning classifier.

---

## How to Extend

### Add a New Genre Profile

Add an entry to `GENRE_PROFILES` in `genres.py`:

```python
GENRE_PROFILES["Rock"] = GenreProfile(
    name="Rock",
    epsilon_ms=12.0,
    epsilon_range=(8.0, 18.0),
    swing_factor=0.10,
    pocket_description="driving, slightly ahead",
    bpm=130.0,
    velocity_mean=95,
    velocity_std=12,
    distribution="gaussian",
    ahead_bias=-3.0,  # rock drummers often push
)
```

Then update `_match_genre()` in `deadband_groove.py` to include the new genre in its lookup list.

### Add a New Microtiming Feature

Features are computed in `extract_microtiming()` or in post-processing. To add, e.g., syncopation detection:

1. Add a field to `TrackTiming` or `GrooveTiming`.
2. Compute it in the loop inside `extract_microtiming()`.
3. Add it to the output.

Example:

```python
@dataclass
class TrackTiming:
    # ... existing fields ...
    syncopation_index: float = 0.0  # NEW

def _compute_syncopation(onsets, grid_division):
    """Ratio of off-beat onsets to total onsets."""
    if not onsets:
        return 0.0
    offbeat = sum(1 for o in onsets if round(o.beat * grid_division) % grid_division != 0)
    return offbeat / len(onsets)
```

### Add a New Visualization

Add a function to `visualize.py`:

```python
def plot_deviation_histogram(
    timing: GrooveTiming,
    bins: int = 50,
    save_path: Optional[Path] = None,
) -> plt.Figure:
    """Histogram of microtiming deviations across all tracks."""
    fig, ax = plt.subplots()
    all_devs = [o.deviation_ms for t in timing.tracks for o in t.onsets]
    ax.hist(all_devs, bins=bins, edgecolor="black", alpha=0.7)
    ax.set_xlabel("Deviation (ms)")
    ax.set_ylabel("Count")
    if save_path:
        fig.savefig(str(save_path), dpi=150)
    return fig
```

### Add a Custom Funnel Model

The default funnel is exponential decay. To add, e.g., a linear funnel:

```python
def build_linear_funnel(timing, epsilon_0, decay_per_beat):
    """Linear deadband narrowing: ε(t) = max(0, ε₀ - decay·t)"""
    # Similar to build_funnel but with linear decay
    ...
```

---

## Testing

### Running Tests

```bash
cd groove-analyzer
pytest                          # all tests (11/11 pass ✅)
pytest tests/test_microtiming.py
pytest tests/test_visualize.py
```

### Test Structure

| File | What it tests |
|------|---------------|
| `test_microtiming.py` | Onset extraction, grid snapping, timing classification, swing computation |
| `test_visualize.py` | Plot generation, figure dimensions, save behavior |

### Writing New Tests

Follow the existing pattern:

```python
import pytest
from pathlib import Path
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import fit_deadband

def test_fit_deadband_coverage():
    """Fitted deadband should achieve at least the target coverage."""
    timing = extract_microtiming("test_data/funk.mid")
    fit = fit_deadband(timing, coverage_target=0.90)
    assert fit.coverage >= 0.90

def test_genre_match():
    """Known genre file should match its genre profile."""
    timing = extract_microtiming("test_data/edm.mid")
    fit = fit_deadband(timing)
    assert fit.genre_match == "EDM"
```

### Testing Philosophy

- **Test with real MIDI data.** Generate test fixtures via `synthesize_groove()` with fixed seeds.
- **Test properties, not exact values.** Coverage should exceed target, not equal a specific number.
- **Round-trip tests.** Generate → extract → fit → verify the genre matches.
- **All 11 tests pass.** No known failures.

---

## Contributing

1. Fork the repo.
2. Create a feature branch: `git checkout -b feature/syncopation-index`.
3. Add code + tests. New features need test coverage.
4. Run `pytest` — all tests must pass.
5. Submit a PR.

### Code Style

- **Type hints everywhere.** All public functions have full type annotations.
- **Docstrings with Parameters/Returns sections.** NumPy convention.
- **Dataclasses for structured data.** No raw dicts where a dataclass makes sense.
- **No global state.** Functions are pure where possible.
- **mido for MIDI I/O.** No other MIDI libraries.

### Commit Messages

```
feat: add Rock genre profile
fix: correct swing calculation for triple-meter files
docs: add histogram visualization recipe
test: add round-trip test for EDM generation
```

### Project Structure

```
groove-analyzer/
├── groove_analyzer/
│   ├── __init__.py
│   ├── microtiming.py      # Core extraction
│   ├── deadband_groove.py  # Deadband theory
│   ├── genres.py           # Profiles + generation
│   └── visualize.py        # Matplotlib plots
├── tests/
│   ├── test_microtiming.py
│   └── test_visualize.py
├── analyze_grooves.py      # CLI script
├── setup.py
├── README.md
└── docs/
    ├── USER-GUIDE.md
    └── DEVELOPER-GUIDE.md
```
