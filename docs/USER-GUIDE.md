# groove-analyzer — User Guide

Complete walkthrough of microtiming extraction, deadband fitting, genre profiles, visualization, and synthetic groove generation.

## Table of Contents

1. [Extracting Microtiming](#extracting-microtiming)
2. [Fitting the Deadband](#fitting-the-deadband)
3. [Building the Funnel](#building-the-funnel)
4. [Proving Groove = Deadband](#proving-groove--deadband)
5. [Genre Profiles](#genre-profiles)
6. [Synthetic Groove Generation](#synthetic-groove-generation)
7. [Visualization](#visualization)
8. [Configuration Options](#configuration-options)
9. [Common Recipes](#common-recipes)
10. [Troubleshooting](#troubleshooting)

---

## Extracting Microtiming

The core function parses a MIDI file and measures how each note onset deviates from a quantized grid.

```python
from groove_analyzer.microtiming import extract_microtiming

timing = extract_microtiming(
    "drums.mid",
    grid_division=16,    # 16th-note grid (4 = quarter, 8 = 8th, 16 = 16th)
    pocket_ms=None,      # auto-computed from data (1.5 × median absolute deviation)
)
```

### Output Structure

```python
# Global statistics
print(f"BPM: {timing.bpm:.1f}")
print(f"Global offset: {timing.global_avg_offset_ms:.2f} ms")
print(f"Global spread: {timing.global_std_offset_ms:.2f} ms")
print(f"Swing factor: {timing.global_swing_factor:.2f}")

# Per-track statistics
for track in timing.tracks:
    print(f"\n{track.track_name}:")
    print(f"  Avg offset: {track.avg_offset_ms:.2f} ms")
    print(f"  Std offset: {track.std_offset_ms:.2f} ms")
    print(f"  Swing: {track.swing_factor:.2f}")
    print(f"  Pocket: {track.pocket_pct:.0f}%")
    print(f"  Ahead: {track.ahead_pct:.0f}%")
    print(f"  Behind: {track.behind_pct:.0f}%")
    print(f"  {len(track.onsets)} onsets")
```

### Expected Output

```
BPM: 120.0
Global offset: 3.45 ms
Global spread: 12.30 ms
Swing factor: 0.35

Kick:
  Avg offset: 2.10 ms
  Std offset: 5.40 ms
  Swing: 0.12
  Pocket: 85%
  Ahead: 8%
  Behind: 7%
  32 onsets

Snare:
  Avg offset: 8.50 ms
  Std offset: 10.20 ms
  Swing: 0.45
  Pocket: 72%
  Ahead: 5%
  Behind: 23%
  16 onsets
```

### Onset Events

Each onset has full timing data:

```python
for onset in timing.tracks[0].onsets[:3]:
    print(f"Beat {onset.beat:.2f}: pitch={onset.pitch}, "
          f"dev={onset.deviation_ms:+.1f}ms ({onset.timing_class.value})")
# Beat 0.00: pitch=36, dev=+2.3ms (pocket)
# Beat 1.00: pitch=36, dev=-1.1ms (pocket)
# Beat 1.25: pitch=42, dev=+5.7ms (pocket)
```

### Timing Classification

| Class | Meaning | Condition |
|-------|---------|-----------|
| `POCKET` | In the groove | `|deviation| ≤ pocket_ms` |
| `AHEAD` | Pushing the beat | `deviation < -pocket_ms` |
| `BEHIND` | Laying back | `deviation > +pocket_ms` |

---

## Fitting the Deadband

The deadband ε is the tolerance corridor that contains the groove pocket.

```python
from groove_analyzer.deadband_groove import fit_deadband

fit = fit_deadband(
    timing,
    coverage_target=0.90,  # 90% of onsets should fall inside ε
    delta_mult=2.5,         # anomaly threshold = 2.5 × ε
)

print(f"Deadband ε: {fit.epsilon_ms:.1f} ms")
print(f"Anomaly δ: {fit.delta_ms:.1f} ms")
print(f"Coverage: {fit.coverage*100:.1f}%")
print(f"Anomaly rate: {fit.anomaly_rate*100:.1f}%")
print(f"Genre match: {fit.genre_match}")
print(f"Confidence: {fit.confidence:.2f}")
```

### Expected Output

```
Deadband ε: 15.2 ms
Anomaly δ: 38.0 ms
Coverage: 91.3%
Anomaly rate: 2.1%
Genre match: Funk
Confidence: 0.87
```

### How It Works

1. Collect absolute deviations of all onsets across all tracks.
2. Sort by magnitude and find the ε that covers `coverage_target` (e.g., 90th percentile).
3. Set δ = `delta_mult × ε`.
4. Compute coverage (fraction inside ε) and anomaly rate (fraction outside δ).
5. Confidence measures how sharply onsets cluster inside ε vs. overall spread.
6. Match ε to the closest genre profile.

---

## Building the Funnel

The funnel models how the deadband narrows over time as the ensemble locks in.

```python
from groove_analyzer.deadband_groove import build_funnel

funnel = build_funnel(
    timing,
    epsilon_0=None,      # defaults to fit_deadband().epsilon_ms
    decay_rate=0.05,     # exponential decay per beat
    delta_mult=2.5,
)

print(f"Initial ε₀: {funnel.deadband_ms:.1f} ms")
print(f"Anomaly δ: {funnel.delta_ms:.1f} ms")
print(f"Decay rate: {funnel.decay_rate}")

# Per-player funnel states
for name, states in funnel.player_funnels.items():
    for s in states[:3]:
        print(f"  {name} beat {s.beat:.1f}: dev={s.deviation_ms:+.1f}ms, "
              f"phase={s.phase}, ε(t)={s.epsilon_at_beat:.1f}ms")
```

### Expected Output

```
Initial ε₀: 15.2 ms
Anomaly δ: 38.0 ms
Decay rate: 0.05

  Kick beat 0.0: dev=+2.3ms, phase=narrowing, ε(t)=15.2ms
  Kick beat 1.0: dev=-1.1ms, phase=narrowing, ε(t)=14.5ms
  Kick beat 1.25: dev=+5.7ms, phase=narrowing, ε(t)=14.1ms
```

### Funnel Phases

| Phase | Condition | Meaning |
|-------|-----------|---------|
| `narrowing` | `|deviation| ≤ ε(t)` | Onset is inside the narrowing deadband |
| `approach` | `ε(t) < |deviation| ≤ δ` | Onset is outside the deadband but not anomalous |
| `anomaly` | `|deviation| > δ` | Onset breaks the groove |

The funnel equation: **ε(t) = ε₀ · e^(-λ·t)** where t is in beats and λ is the decay rate.

---

## Proving Groove = Deadband

The proof has three quantitative pillars:

```python
from groove_analyzer.deadband_groove import prove_groove_is_deadband

proof = prove_groove_is_deadband(timing)
for key, value in proof.items():
    print(f"{key}: {value}")
```

### Expected Output

```
coverage: 0.913
variance_collapse: 0.872
genre_coherence: 0.943
epsilon_ms: 15.2
delta_ms: 38.0
genre_match: Funk
```

### The Three Pillars

1. **Coverage**: Fraction of onsets inside ε. High coverage (>0.85) means the deadband contains the groove.

2. **Variance collapse**: Ratio of variance inside ε to overall variance. High collapse (>0.8) means the deadband concentrates the timing distribution.

3. **Genre coherence**: How close ε is to the characteristic value for the matched genre. High coherence (>0.8) means the genre profile explains the data.

---

## Genre Profiles

Five built-in profiles covering common genres:

```python
from groove_analyzer.genres import GENRE_PROFILES

for name, prof in GENRE_PROFILES.items():
    print(f"{name}: ε={prof.epsilon_ms}ms, swing={prof.swing_factor}, "
          f"bpm={prof.bpm}, dist={prof.distribution}, bias={prof.ahead_bias}ms")
```

### Profile Details

| Genre | ε (ms) | Range | Swing | BPM | Vel mean | Distribution | Bias |
|-------|--------|-------|-------|-----|----------|-------------|------|
| EDM | 3 | 1–5 | 0.0 | 128 | 100 | uniform | 0 ms |
| Funk | 15 | 10–20 | 0.15 | 105 | 95 | gaussian | +5 ms (laid back) |
| Hip-hop | 20 | 15–25 | 0.35 | 90 | 80 | gaussian | +8 ms (laid back) |
| Latin | 30 | 20–40 | 0.50 | 110 | 85 | triangular | −5 ms (pushing) |
| Jazz | 40 | 30–50 | 0.75 | 120 | 70 | triangular | −10 ms (pushing) |

### Profile Fields

Each `GenreProfile` has:

- `epsilon_ms` — characteristic deadband half-width
- `epsilon_range` — (low, high) bounds for random sampling
- `swing_factor` — 0.0 (even) to 1.0 (full triplet)
- `pocket_description` — human-readable
- `bpm` — typical tempo
- `velocity_mean` / `velocity_std` — MIDI velocity parameters
- `distribution` — "uniform", "triangular", or "gaussian"
- `ahead_bias` — mean offset in ms (negative = ahead, positive = behind)

---

## Synthetic Groove Generation

Generate MIDI files with genre-appropriate microtiming:

```python
from groove_analyzer.genres import synthesize_groove

# Generate a 4-bar funk groove
mid = synthesize_groove(
    "Funk",
    bars=4,
    seed=42,
    output_path="funk_groove.mid",
)

# Custom drum pattern (16th-note indices per bar)
custom_parts = {
    "Kick": [0, 6, 8, 14],
    "Snare": [4, 12],
    "HiHat": [0, 2, 4, 6, 8, 10, 12, 14],
}
mid = synthesize_groove("Hip-hop", bars=2, parts=custom_parts, seed=42)
```

### Default Patterns

Each genre has a default drum pattern:

- **EDM/Funk/Hip-hop**: Kick on 1 and 3, Snare on 2 and 4, HiHat on all 8th notes
- **Jazz**: Ride cymbal pattern, cross-stick snare, kick on 1, &-of-2, &-of-3
- **Latin**: Conga, Clave, Timbales, Bass patterns

### Generate All Genres

```python
from groove_analyzer.genres import generate_all_genre_examples

paths = generate_all_genre_examples("output/", bars=4, seed=42)
# [PosixPath('output/edm_groove.mid'), PosixPath('output/funk_groove.mid'),
#  PosixPath('output/hiphop_groove.mid'), PosixPath('output/latin_groove.mid'),
#  PosixPath('output/jazz_groove.mid')]
```

---

## Visualization

### Single-File Funnel Plot

```python
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.visualize import plot_deadband_funnel

timing = extract_microtiming("performance.mid")
fig = plot_deadband_funnel(
    timing,
    title="My Performance — Groove Funnel",
    save_path="my_funnel.png",
    figsize=(12, 6),
)
```

The plot shows:
- **Scatter points**: each onset, colored by instrument
- **Green shaded region**: deadband ε(t), narrowing over time
- **Orange region**: approach zone (between ε and δ)
- **Red dashed lines**: anomaly threshold δ
- **Annotation box**: ε, δ, coverage, genre match

### Multi-Genre Comparison

```python
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.visualize import plot_groove_comparison

timings = {
    "Funk": extract_microtiming("funk.mid"),
    "Jazz": extract_microtiming("jazz.mid"),
    "EDM": extract_microtiming("edm.mid"),
}

fig = plot_groove_comparison(timings, save_path="comparison.png")
```

This produces a grid of funnel plots (up to 3 columns), each with its own deadband fit.

---

## Configuration Options

### extract_microtiming

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `Path \| str` | required | Path to MIDI file |
| `grid_division` | `int` | 16 | Grid resolution: 4=quarter, 8=8th, 16=16th |
| `pocket_ms` | `float \| None` | None | Pocket threshold in ms. Auto=1.5×MAD |

### fit_deadband

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timing` | `GrooveTiming` | required | Output of `extract_microtiming` |
| `coverage_target` | `float` | 0.90 | Fraction of onsets to contain inside ε |
| `delta_mult` | `float` | 2.5 | Multiplier from ε to anomaly threshold δ |

### build_funnel

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timing` | `GrooveTiming` | required | Output of `extract_microtiming` |
| `epsilon_0` | `float \| None` | None | Initial deadband width. Auto=fit result |
| `decay_rate` | `float` | 0.05 | Exponential decay rate per beat |
| `delta_mult` | `float` | 2.5 | Multiplier for anomaly threshold |

### synthesize_groove

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `genre` | `str` | required | Key in `GENRE_PROFILES` |
| `bars` | `int` | 4 | Number of bars |
| `parts` | `Dict[str, List[int]] \| None` | None | Instrument → 16th-note indices. Auto=genre default |
| `seed` | `int \| None` | None | RNG seed for reproducibility |
| `output_path` | `Path \| str \| None` | None | Save MIDI file here |

### plot_deadband_funnel

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timing` | `GrooveTiming` | required | Timing data |
| `funnel` | `EnsembleFunnel \| None` | None | Pre-built funnel. Auto=build_funnel |
| `title` | `str` | "Groove = Deadband Funnel" | Plot title |
| `save_path` | `Path \| str \| None` | None | Save image here |
| `figsize` | `tuple` | (12, 6) | Figure size in inches |

---

## Common Recipes

### 1. Analyze a Full Drum Performance

```python
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import fit_deadband, prove_groove_is_deadband
from groove_analyzer.visualize import plot_deadband_funnel

timing = extract_microtiming("studio_take_3.mid")
fit = fit_deadband(timing)
proof = prove_groove_is_deadband(timing)

print(f"ε = {fit.epsilon_ms:.1f} ms")
print(f"Genre: {fit.genre_match}")
print(f"Proof: coverage={proof['coverage']:.2f}, "
      f"variance_collapse={proof['variance_collapse']:.2f}")

plot_deadband_funnel(timing, save_path="take3_funnel.png")
```

### 2. Compare Multiple Takes

```python
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import fit_deadband

takes = {
    f"Take {i}": extract_microtiming(f"take_{i}.mid")
    for i in range(1, 6)
}

for name, timing in takes.items():
    fit = fit_deadband(timing)
    print(f"{name}: ε={fit.epsilon_ms:.1f}ms, "
          f"coverage={fit.coverage:.0%}, genre={fit.genre_match}")
```

### 3. Generate Genre Examples and Analyze Them

```python
from groove_analyzer.genres import generate_all_genre_examples
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import fit_deadband

paths = generate_all_genre_examples("genre_examples/", bars=8, seed=42)

for path in paths:
    timing = extract_microtiming(path)
    fit = fit_deadband(timing)
    print(f"{path.name}: ε={fit.epsilon_ms:.1f}ms, genre={fit.genre_match}")
```

### 4. Custom Pocket Threshold

```python
from groove_analyzer.microtiming import extract_microtiming

# Tight pocket: 10ms threshold
timing = extract_microtiming("performance.mid", pocket_ms=10.0)

for track in timing.tracks:
    print(f"{track.track_name}: pocket={track.pocket_pct:.0f}%")
```

### 5. Build a Funnel with Custom Decay

```python
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import build_funnel

timing = extract_microtiming("performance.mid")

# Slow decay — ensemble takes a long time to lock
funnel = build_funnel(timing, decay_rate=0.02)

# Fast decay — ensemble locks quickly
funnel = build_funnel(timing, decay_rate=0.10)

# Inspect phase transitions for a player
for state in funnel.player_funnels["Kick"][:10]:
    if state.phase == "anomaly":
        print(f"Anomaly at beat {state.beat:.1f}! dev={state.deviation_ms:+.1f}ms")
```

### 6. Batch Processing

```python
from pathlib import Path
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import fit_deadband
from groove_analyzer.visualize import plot_deadband_funnel

midi_dir = Path("midi_files/")
results = []

for mid_file in sorted(midi_dir.glob("*.mid")):
    timing = extract_microtiming(mid_file)
    fit = fit_deadband(timing)
    results.append((mid_file.name, fit))
    plot_deadband_funnel(
        timing,
        title=mid_file.stem,
        save_path=f"funnels/{mid_file.stem}.png",
    )

# Summary
for name, fit in sorted(results, key=lambda x: x[1].epsilon_ms):
    print(f"{name}: ε={fit.epsilon_ms:.1f}ms, {fit.genre_match}")
```

---

## Troubleshooting

### `extract_microtiming` returns empty tracks

The MIDI file may have no note_on events with velocity > 0, or all events may be on track 0 (conductor track). Check:

```python
import mido
mid = mido.MidiFile("file.mid")
for i, track in enumerate(mid.tracks):
    note_ons = [m for m in track if m.type == "note_on" and m.velocity > 0]
    print(f"Track {i}: {len(note_ons)} note_on events")
```

### Coverage is very low (< 0.5)

The MIDI file may have very loose timing or be poorly quantized. Try:

1. Increase `coverage_target` to 0.95 or higher.
2. Increase `delta_mult` to give more room before anomaly classification.
3. Use a coarser `grid_division` (8 instead of 16).

### Genre match seems wrong

Genre matching is based purely on ε proximity to genre centers. A file with ε=18ms will match "Funk" (15ms) even if it's actually a loose pop recording. The genre profiles are reference values, not classifiers.

### Swing factor is always 0

Swing detection requires:
- 16th-note grid (`grid_division=16`)
- Enough off-beat (odd 16th) events
- A perceptible difference between odd and even 16th timing

If the MIDI file is fully quantized or has no off-beat notes, swing will be 0.

### Matplotlib display issues

If running headless (server, CI), use the Agg backend:

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
```

The `save_path` parameter writes to disk regardless of display backend.
