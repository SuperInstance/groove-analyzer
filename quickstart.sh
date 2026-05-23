#!/bin/bash
# groove-analyzer quickstart — analyze genre grooves, prove groove = deadband
set -e
echo "🥁 Groove Analyzer — Quick Start"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

pip install -e . --quiet 2>/dev/null || true

python3 << 'PYEOF'
from groove_analyzer.genres import GENRE_PROFILES, generate_all_genre_examples
from groove_analyzer.microtiming import extract_microtiming
from groove_analyzer.deadband_groove import fit_deadband, prove_groove_is_deadband
import tempfile
from pathlib import Path

print('Genre profiles:')
for name, prof in GENRE_PROFILES.items():
    print(f'  {name:12s}  ε=[{prof.epsilon_range[0]:.0f}, {prof.epsilon_range[1]:.0f}] ms  swing={prof.swing_factor:.2f}')

# Generate grooves and analyze funk
tmpdir = Path(tempfile.mkdtemp())
paths = generate_all_genre_examples(tmpdir, bars=4, seed=42)
funk_path = [p for p in paths if 'funk' in p.name][0]

gt = extract_microtiming(funk_path)
fit = fit_deadband(gt)
proof = prove_groove_is_deadband(gt)

print(f'\n📊 Funk groove analysis:')
print(f'   BPM: {gt.bpm:.1f}')
print(f'   Tracks: {len(gt.tracks)}')
print(f'   Fitted ε: {fit.epsilon_ms:.2f} ms')
print(f'   Coverage: {fit.coverage*100:.1f}%')
print(f'   Genre match: {fit.genre_match}')
print(f'   Variance collapse: {proof["variance_collapse"]:.3f}')
print(f'   Genre coherence: {proof["genre_coherence"]:.3f}')

print()
print('✅ groove-analyzer works!')
PYEOF
