"""Tests for microtiming extraction."""

from pathlib import Path

import mido
import pytest

from groove_analyzer.microtiming import (
    TimingClass,
    extract_microtiming,
    _snap_to_grid,
    _classify_deviation,
)
from groove_analyzer.genres import synthesize_groove, GENRE_PROFILES, generate_all_genre_examples
from groove_analyzer.deadband_groove import fit_deadband, build_funnel, prove_groove_is_deadband


@pytest.fixture
def simple_midi(tmp_path: Path) -> Path:
    mid = mido.MidiFile(ticks_per_beat=480)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name", name="Meta", time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))  # 120 BPM
    meta.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(meta)

    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name="Kick", time=0))
    for i in range(4):
        delta_on = 0 if i == 0 else 380
        track.append(mido.Message("note_on", note=36, velocity=100, time=delta_on))
        track.append(mido.Message("note_off", note=36, velocity=0, time=100))
    track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(track)

    path = tmp_path / "simple.mid"
    mid.save(str(path))
    return path


def test_snap_to_grid():
    assert _snap_to_grid(0.0, 4) == 0.0
    assert _snap_to_grid(0.12, 4) == 0.0
    assert _snap_to_grid(0.13, 4) == 0.25
    assert _snap_to_grid(1.0, 4) == 1.0


def test_classify_deviation():
    assert _classify_deviation(0.0, 10.0) == TimingClass.POCKET
    assert _classify_deviation(5.0, 10.0) == TimingClass.POCKET
    assert _classify_deviation(15.0, 10.0) == TimingClass.BEHIND
    assert _classify_deviation(-15.0, 10.0) == TimingClass.AHEAD


def test_extract_basic(simple_midi: Path):
    gt = extract_microtiming(simple_midi, grid_division=4)
    assert gt.bpm == 120.0
    assert len(gt.tracks) == 1
    assert gt.tracks[0].track_name == "Kick"
    assert len(gt.tracks[0].onsets) == 4
    # Perfect grid -> deviations near zero
    for o in gt.tracks[0].onsets:
        assert abs(o.deviation_ms) < 1.0


def test_genre_synthesis(tmp_path: Path):
    path = tmp_path / "funk.mid"
    mid = synthesize_groove("Funk", bars=2, seed=42, output_path=path)
    assert path.exists()
    assert len(mid.tracks) >= 2  # meta + at least one part


def test_all_genres_generated(tmp_path: Path):
    paths = generate_all_genre_examples(tmp_path, bars=2, seed=123)
    assert len(paths) == len(GENRE_PROFILES)
    for p in paths:
        assert p.exists()


def test_deadband_fit(tmp_path: Path):
    paths = generate_all_genre_examples(tmp_path, bars=4, seed=42)
    for p in paths:
        gt = extract_microtiming(p)
        fit = fit_deadband(gt)
        assert fit.epsilon_ms > 0
        assert fit.delta_ms > fit.epsilon_ms
        assert 0.0 <= fit.coverage <= 1.0
        assert fit.genre_match is not None


def test_funnel_build(tmp_path: Path):
    paths = generate_all_genre_examples(tmp_path, bars=4, seed=42)
    for p in paths:
        gt = extract_microtiming(p)
        funnel = build_funnel(gt)
        assert funnel.deadband_ms > 0
        assert funnel.delta_ms > funnel.deadband_ms
        for states in funnel.player_funnels.values():
            for s in states:
                assert s.phase in ("narrowing", "approach", "anomaly")


def test_prove_groove_is_deadband(tmp_path: Path):
    # EDM should have very high coverage and genre match
    path = tmp_path / "edm_groove.mid"
    synthesize_groove("EDM", bars=4, seed=42, output_path=path)
    gt = extract_microtiming(path)
    proof = prove_groove_is_deadband(gt)
    assert proof["coverage"] >= 0.8
    # Variance collapse can be low for uniform distributions (e.g. EDM)
    # where the spread is already tight and near-constant.
    assert proof["variance_collapse"] >= 0.0
    assert proof["genre_match"] == "EDM"


def test_jazz_wider_than_edm(tmp_path: Path):
    synthesize_groove("EDM", bars=4, seed=1, output_path=tmp_path / "e.mid")
    synthesize_groove("Jazz", bars=4, seed=1, output_path=tmp_path / "j.mid")
    fit_edm = fit_deadband(extract_microtiming(tmp_path / "e.mid"))
    fit_jazz = fit_deadband(extract_microtiming(tmp_path / "j.mid"))
    assert fit_jazz.epsilon_ms > fit_edm.epsilon_ms
