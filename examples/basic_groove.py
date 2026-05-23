#!/usr/bin/env python3
"""
basic_groove.py — Synthesize and analyze a simple groove.

Demonstrates:
- Synthesizing a Funk groove as a MIDI file
- Extracting microtiming data from the MIDI
- Fitting a deadband to the microtiming
- Proving the groove is a deadband funnel

Run:  python3 examples/basic_groove.py
"""

import tempfile
from pathlib import Path

from groove_analyzer import (
    synthesize_groove,
    extract_microtiming,
    fit_deadband,
    build_funnel,
    prove_groove_is_deadband,
)

# --- Synthesize a Funk groove ---
print("SYNTHESIZING FUNK GROOVE (4 bars)")
print("=" * 50)

with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
    mid_path = Path(tmp.name)

mid = synthesize_groove("Funk", bars=4, seed=42, output_path=mid_path)
print(f"MIDI file: {mid_path}")
print(f"Tracks: {len(mid.tracks)}")
print()

# --- Extract microtiming ---
print("MICROTIMING ANALYSIS")
print("=" * 50)

timing = extract_microtiming(mid_path, grid_division=4)
print(f"BPM: {timing.bpm:.1f}")
print(f"Grid division: {timing.grid_division}")
print(f"Global avg offset: {timing.global_avg_offset_ms:.2f} ms")
print(f"Global std offset: {timing.global_std_offset_ms:.2f} ms")
print(f"Global pocket width: {timing.global_pocket_width_ms:.2f} ms")
print(f"Global swing factor: {timing.global_swing_factor:.2f}")
print()

for track in timing.tracks:
    print(f"  {track}")
    print(f"    Avg offset: {track.avg_offset_ms:.2f} ms")
    print(f"    Std offset: {track.std_offset_ms:.2f} ms")
    print(f"    Swing: {track.swing_factor:.2f}")
    print(f"    Pocket: {track.pocket_pct:.1f}% | Ahead: {track.ahead_pct:.1f}% | Behind: {track.behind_pct:.1f}%")
print()

# --- Fit deadband ---
print("DEADBAND FIT")
print("=" * 50)

fit = fit_deadband(timing)
print(f"Deadband (epsilon): {fit.epsilon_ms:.2f} ms")
print(f"Anomaly threshold (delta): {fit.delta_ms:.2f} ms")
print(f"Coverage: {fit.coverage:.1%} of onsets inside epsilon")
print(f"Anomaly rate: {fit.anomaly_rate:.1%}")
print(f"Closest genre: {fit.genre_match}")
print(f"Confidence: {fit.confidence:.2f}")
print()

# --- Build funnel ---
print("ENSEMBLE FUNNEL")
print("=" * 50)

funnel = build_funnel(timing)
print(f"Funnel: {funnel}")
for name, states in funnel.player_funnels.items():
    phases = [s.phase for s in states]
    n_narrow = phases.count("narrowing")
    n_approach = phases.count("approach")
    n_anomaly = phases.count("anomaly")
    print(f"  {name}: {len(states)} onsets — narrowing={n_narrow}, approach={n_approach}, anomaly={n_anomaly}")
print()

# --- Prove groove = deadband ---
print("PROOF: GROOVE = DEADBAND")
print("=" * 50)

proof = prove_groove_is_deadband(timing)
for key, value in proof.items():
    print(f"  {key}: {value}")

print()
print("The groove pocket IS the deadband epsilon.")
print("When all player offsets lie within e, the ensemble is in the pocket.")

# Cleanup
mid_path.unlink(missing_ok=True)
