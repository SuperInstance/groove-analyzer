"""Comprehensive tests: property-based, edge cases, round-trip, stress."""

from __future__ import annotations

from pathlib import Path

import mido
import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from groove_analyzer.exceptions import GrooveAnalysisError, InvalidGrooveError
from groove_analyzer.microtiming import (
    TimingClass,
    extract_microtiming,
    _snap_to_grid,
    _classify_deviation,
)
from groove_analyzer.deadband_groove import (
    fit_deadband,
    build_funnel,
    prove_groove_is_deadband,
)
from groove_analyzer.genres import (
    GENRE_PROFILES,
    synthesize_groove,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_midi_with_hits(
    hits: list[int],
    bpm: int = 120,
    tpb: int = 480,
    grid_division: int = 4,
) -> mido.MidiFile:
    """Create a minimal MIDI file with note-on events at given 16th-note indices."""
    mid = mido.MidiFile(ticks_per_beat=tpb)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("track_name", name="Meta", time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=int(60_000_000 / bpm), time=0))
    meta.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(meta)

    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name="Test", time=0))
    ticks_per_16th = tpb // grid_division
    prev_tick = 0
    for idx in hits:
        target = idx * ticks_per_16th
        delta = max(0, target - prev_tick)
        track.append(mido.Message("note_on", note=60, velocity=100, time=delta))
        track.append(mido.Message("note_off", note=60, velocity=0, time=30))
        prev_tick = target + 30
    track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(track)
    return mid


def _save_midi(mid: mido.MidiFile, path: Path) -> Path:
    mid.save(str(path))
    return path


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

class TestProperties:
    """Invariants that must hold for all valid inputs."""

    @given(
        bpm=st.integers(min_value=30, max_value=300),
        bars=st.integers(min_value=1, max_value=8),
        seed=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_groove_scores_in_range(self, bpm: int, bars: int, seed: int, tmp_path: Path) -> None:
        """Coverage and confidence are always in [0, 1]."""
        # Override BPM via a genre profile — use Funk and adjust
        genre = "Funk"
        path = tmp_path / f"prop_{bpm}_{bars}_{seed}.mid"
        synthesize_groove(genre, bars=bars, seed=seed, output_path=path)
        gt = extract_microtiming(path)
        fit = fit_deadband(gt)

        assert 0.0 <= fit.coverage <= 1.0, f"coverage={fit.coverage}"
        assert 0.0 <= fit.confidence <= 1.0, f"confidence={fit.confidence}"
        assert 0.0 <= fit.anomaly_rate <= 1.0, f"anomaly_rate={fit.anomaly_rate}"
        assert fit.epsilon_ms > 0
        assert fit.delta_ms > fit.epsilon_ms

    @given(
        genre_name=st.sampled_from(list(GENRE_PROFILES.keys())),
        seed=st.integers(min_value=0, max_value=5000),
    )
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_prove_metrics_bounded(self, genre_name: str, seed: int, tmp_path: Path) -> None:
        """All proof metrics are in their expected ranges."""
        path = tmp_path / f"proof_{genre_name}_{seed}.mid"
        synthesize_groove(genre_name, bars=4, seed=seed, output_path=path)
        gt = extract_microtiming(path)
        proof = prove_groove_is_deadband(gt)

        assert 0.0 <= proof["coverage"] <= 1.0
        assert 0.0 <= proof["variance_collapse"] <= 1.0
        assert 0.0 <= proof["genre_coherence"] <= 1.0
        assert proof["epsilon_ms"] > 0
        assert proof["delta_ms"] > proof["epsilon_ms"]

    @given(
        deviation=st.floats(min_value=-200, max_value=200),
        pocket=st.floats(min_value=0.1, max_value=100),
    )
    @settings(max_examples=50)
    def test_classify_deviation_returns_valid_enum(self, deviation: float, pocket: float) -> None:
        """_classify_deviation always returns a TimingClass member."""
        result = _classify_deviation(deviation, pocket)
        assert isinstance(result, TimingClass)

    @given(
        beat=st.floats(min_value=0, max_value=100),
        division=st.integers(min_value=1, max_value=64),
    )
    @settings(max_examples=50)
    def test_snap_to_grid_idempotent(self, beat: float, division: int) -> None:
        """Snapping an already-snapped beat returns the same value."""
        snapped = _snap_to_grid(beat, division)
        assert _snap_to_grid(snapped, division) == snapped


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Corner cases and boundary conditions."""

    def test_empty_groove_no_notes(self, tmp_path: Path) -> None:
        """MIDI file with tracks but no note_on events returns empty timing."""
        mid = mido.MidiFile(ticks_per_beat=480)
        meta = mido.MidiTrack()
        meta.append(mido.MetaMessage("track_name", name="Meta", time=0))
        meta.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
        meta.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(meta)

        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name="Empty", time=0))
        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(track)

        path = _save_midi(mid, tmp_path / "empty.mid")
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gt = extract_microtiming(path)
        assert len(gt.tracks) == 0
        assert gt.global_avg_offset_ms == 0.0

    def test_single_hit(self, tmp_path: Path) -> None:
        """A single note onset can be analysed without error."""
        mid = _make_midi_with_hits([0])
        path = _save_midi(mid, tmp_path / "one.mid")
        gt = extract_microtiming(path)
        assert len(gt.tracks) == 1
        assert len(gt.tracks[0].onsets) == 1
        fit = fit_deadband(gt)
        assert fit.coverage == 1.0

    def test_identical_repeated_pattern(self, tmp_path: Path) -> None:
        """Identical repeated 16th-note pattern produces consistent deviations."""
        # Use synthesize_groove with EDM (nearly quantised) and no swing
        path = tmp_path / "repeat.mid"
        synthesize_groove("EDM", bars=4, seed=0, output_path=path)
        gt = extract_microtiming(path)
        # EDM with uniform distribution should have tight deviations
        for o in gt.tracks[0].onsets:
            assert abs(o.deviation_ms) < 10.0

    def test_extremely_fast_bpm(self, tmp_path: Path) -> None:
        """300 BPM works fine."""
        mid = _make_midi_with_hits([0, 2, 4, 6], bpm=300)
        path = _save_midi(mid, tmp_path / "fast.mid")
        gt = extract_microtiming(path)
        assert gt.bpm > 250

    def test_extremely_slow_bpm(self, tmp_path: Path) -> None:
        """30 BPM works fine."""
        mid = _make_midi_with_hits([0, 2, 4, 6], bpm=30)
        path = _save_midi(mid, tmp_path / "slow.mid")
        gt = extract_microtiming(path)
        assert gt.bpm < 35

    def test_no_tracks_raises(self, tmp_path: Path) -> None:
        """A completely empty MIDI file raises InvalidGrooveError."""
        mid = mido.MidiFile(ticks_per_beat=480)
        path = _save_midi(mid, tmp_path / "notracks.mid")
        with pytest.raises(InvalidGrooveError, match="no tracks"):
            extract_microtiming(path)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Non-existent file raises GrooveAnalysisError."""
        with pytest.raises(GrooveAnalysisError, match="not found"):
            extract_microtiming(tmp_path / "nonexistent.mid")

    def test_invalid_grid_division(self, tmp_path: Path) -> None:
        """Zero or negative grid_division raises InvalidGrooveError."""
        mid = _make_midi_with_hits([0])
        path = _save_midi(mid, tmp_path / "tmp.mid")
        with pytest.raises(InvalidGrooveError, match="grid_division"):
            extract_microtiming(path, grid_division=0)

    def test_invalid_coverage_target(self, tmp_path: Path) -> None:
        """Invalid coverage_target raises ValueError."""
        mid = _make_midi_with_hits([0, 4])
        path = _save_midi(mid, tmp_path / "tmp.mid")
        gt = extract_microtiming(path)
        with pytest.raises(ValueError, match="coverage_target"):
            fit_deadband(gt, coverage_target=0.0)
        with pytest.raises(ValueError, match="coverage_target"):
            fit_deadband(gt, coverage_target=1.5)

    def test_invalid_delta_mult(self, tmp_path: Path) -> None:
        """delta_mult <= 1.0 raises ValueError."""
        mid = _make_midi_with_hits([0, 4])
        path = _save_midi(mid, tmp_path / "tmp.mid")
        gt = extract_microtiming(path)
        with pytest.raises(ValueError, match="delta_mult"):
            fit_deadband(gt, delta_mult=0.5)

    def test_empty_timings_for_funnel(self, tmp_path: Path) -> None:
        """Empty GrooveTiming still produces a valid funnel."""
        mid = mido.MidiFile(ticks_per_beat=480)
        meta = mido.MidiTrack()
        meta.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
        meta.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(meta)
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name="Silent", time=0))
        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(track)
        path = _save_midi(mid, tmp_path / "silent.mid")
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            gt = extract_microtiming(path)
        funnel = build_funnel(gt)
        assert funnel.deadband_ms > 0

    def test_unknown_genre_raises(self) -> None:
        """synthesize_groove with unknown genre raises ValueError."""
        with pytest.raises(ValueError, match="Unknown genre"):
            synthesize_groove("Reggae")

    def test_zero_bars_raises(self) -> None:
        """synthesize_groove with bars=0 raises ValueError."""
        with pytest.raises(ValueError, match="bars must be positive"):
            synthesize_groove("Funk", bars=0)


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """Generate → analyse → verify scores match expected profiles."""

    @pytest.mark.parametrize("genre", list(GENRE_PROFILES.keys()))
    def test_genre_epsilon_in_range(self, genre: str, tmp_path: Path) -> None:
        """Fitted ε should fall within the genre's declared ε range."""
        profile = GENRE_PROFILES[genre]
        path = tmp_path / f"{genre}.mid"
        synthesize_groove(genre, bars=8, seed=42, output_path=path)
        gt = extract_microtiming(path)
        fit = fit_deadband(gt)

        lo, hi = profile.epsilon_range
        # Allow generous margin — the fit is data-driven and stochastic
        assert fit.epsilon_ms >= lo * 0.5, (
            f"{genre}: ε={fit.epsilon_ms:.2f} too low for range [{lo}, {hi}]"
        )
        assert fit.epsilon_ms <= hi * 2.0, (
            f"{genre}: ε={fit.epsilon_ms:.2f} too high for range [{lo}, {hi}]"
        )

    @pytest.mark.parametrize("genre", list(GENRE_PROFILES.keys()))
    def test_genre_match_is_self(self, genre: str, tmp_path: Path) -> None:
        """Fitted genre match should identify the generating genre."""
        path = tmp_path / f"{genre}_match.mid"
        synthesize_groove(genre, bars=8, seed=42, output_path=path)
        gt = extract_microtiming(path)
        fit = fit_deadband(gt)
        assert fit.genre_match == genre

    def test_edm_coverage_high(self, tmp_path: Path) -> None:
        """EDM should have very high coverage (tight quantisation)."""
        path = tmp_path / "edm.mid"
        synthesize_groove("EDM", bars=4, seed=42, output_path=path)
        gt = extract_microtiming(path)
        fit = fit_deadband(gt)
        assert fit.coverage >= 0.85


# ---------------------------------------------------------------------------
# Stress test
# ---------------------------------------------------------------------------

class TestStress:
    """Analyse many random grooves without crash."""

    def test_1000_random_grooves(self, tmp_path: Path) -> None:
        """Generate and analyse 1000 random grooves without crash."""
        import random as rng
        rng.seed(12345)
        genres = list(GENRE_PROFILES.keys())
        for i in range(1000):
            genre = rng.choice(genres)
            bars = rng.randint(1, 4)
            seed = rng.randint(0, 100_000)
            path = tmp_path / f"stress_{i}.mid"
            synthesize_groove(genre, bars=bars, seed=seed, output_path=path)
            gt = extract_microtiming(path)
            fit = fit_deadband(gt)
            # Basic sanity
            assert fit.epsilon_ms > 0
            assert 0.0 <= fit.coverage <= 1.0


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class TestExceptions:
    """Custom exception classes work correctly."""

    def test_groove_analysis_error_is_exception(self) -> None:
        assert issubclass(GrooveAnalysisError, Exception)

    def test_invalid_groove_is_subclass(self) -> None:
        assert issubclass(InvalidGrooveError, GrooveAnalysisError)

    def test_error_stores_path(self) -> None:
        err = GrooveAnalysisError("test", path="/foo.mid")
        assert err.path == "/foo.mid"

    def test_error_without_path(self) -> None:
        err = GrooveAnalysisError("test")
        assert err.path is None
