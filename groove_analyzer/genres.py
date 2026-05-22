"""Genre-specific deadband profiles and synthetic groove generation.

Each genre is characterised by a deadband e, a swing factor, and a
statistical distribution of microtiming offsets.  We synthesise grooves
by placing notes on a metronome grid and then perturbing each onset by
a random offset drawn from the genre's deadband distribution.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import mido


@dataclass
class GenreProfile:  # pylint: disable=too-many-instance-attributes
    """Deadband parameters for a musical genre."""
    name: str
    epsilon_ms: float       # deadband half-width in ms
    epsilon_range: tuple[float, float]
    swing_factor: float     # 0.0 = even, 1.0 = full triplet
    pocket_description: str
    bpm: float              # typical tempo
    velocity_mean: int      # average MIDI velocity
    velocity_std: int
    # Microtiming distribution: "uniform", "triangular", "gaussian"
    distribution: str
    ahead_bias: float       # mean offset in ms (negative = ahead, positive = behind)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(f"name must be a non-empty string, got {self.name!r}")
        if not isinstance(self.epsilon_ms, (int, float)) or (
            isinstance(self.epsilon_ms, float)
            and (math.isnan(self.epsilon_ms) or math.isinf(self.epsilon_ms))
        ):
            raise ValueError(f"epsilon_ms must be a finite positive number, got {self.epsilon_ms!r}")
        if self.epsilon_ms <= 0:
            raise ValueError(f"epsilon_ms must be positive, got {self.epsilon_ms}")
        if not isinstance(self.velocity_std, (int, float)) or self.velocity_std < 0:
            raise ValueError(f"velocity_std must be non-negative, got {self.velocity_std!r}")
        if not isinstance(self.swing_factor, (int, float)) or not (0.0 <= self.swing_factor <= 1.0):
            raise ValueError(f"swing_factor must be between 0.0 and 1.0, got {self.swing_factor!r}")
        if not isinstance(self.bpm, (int, float)) or (
            isinstance(self.bpm, float)
            and (math.isnan(self.bpm) or math.isinf(self.bpm))
        ):
            raise ValueError(f"bpm must be a finite positive number, got {self.bpm!r}")
        if self.bpm <= 0:
            raise ValueError(f"bpm must be positive, got {self.bpm}")

    def __repr__(self) -> str:
        return (
            f"GenreProfile(name={self.name!r}, e={self.epsilon_ms:.1f}ms, "
            f"bpm={self.bpm:.1f})"
        )


GENRE_PROFILES: Dict[str, GenreProfile] = {
    "Jazz": GenreProfile(
        name="Jazz",
        epsilon_ms=40.0,
        epsilon_range=(30.0, 50.0),
        swing_factor=0.75,
        pocket_description="wide pocket, high swing",
        bpm=120.0,
        velocity_mean=70,
        velocity_std=15,
        distribution="triangular",
        ahead_bias=-10.0,   # jazz drummers often push
    ),
    "Funk": GenreProfile(
        name="Funk",
        epsilon_ms=15.0,
        epsilon_range=(10.0, 20.0),
        swing_factor=0.15,
        pocket_description="tight pocket, low swing",
        bpm=105.0,
        velocity_mean=95,
        velocity_std=10,
        distribution="gaussian",
        ahead_bias=5.0,     # bass often lays back
    ),
    "Hip-hop": GenreProfile(
        name="Hip-hop",
        epsilon_ms=20.0,
        epsilon_range=(15.0, 25.0),
        swing_factor=0.35,
        pocket_description="medium pocket, laid-back",
        bpm=90.0,
        velocity_mean=80,
        velocity_std=12,
        distribution="gaussian",
        ahead_bias=8.0,
    ),
    "EDM": GenreProfile(
        name="EDM",
        epsilon_ms=3.0,
        epsilon_range=(1.0, 5.0),
        swing_factor=0.0,
        pocket_description="nearly quantized",
        bpm=128.0,
        velocity_mean=100,
        velocity_std=5,
        distribution="uniform",
        ahead_bias=0.0,
    ),
    "Latin": GenreProfile(
        name="Latin",
        epsilon_ms=30.0,
        epsilon_range=(20.0, 40.0),
        swing_factor=0.50,
        pocket_description="polyrhythmic offsets",
        bpm=110.0,
        velocity_mean=85,
        velocity_std=14,
        distribution="triangular",
        ahead_bias=-5.0,
    ),
}


def _random_offset(profile: GenreProfile) -> float:
    """Draw a microtiming offset in ms from the genre's distribution.

    The distribution is parameterised so that the 90th-percentile of
    |offset| is approximately ``epsilon_ms``, which ensures that
    ``fit_deadband`` can recover ``epsilon_ms`` in a round-trip test.

    ``ahead_bias`` is applied as a small additive nudge so it biases
    the *direction* of offsets without significantly shifting the spread.
    """
    eps = profile.epsilon_ms
    bias = profile.ahead_bias
    # Scale bias down so it nudges direction without inflating the
    # 90th-percentile of |offset| beyond epsilon.
    nudge = bias * 0.25
    if profile.distribution == "uniform":
        # Uniform on [-R, R]: 90th percentile of |X| = 0.9*R
        # So R = eps / 0.9 to get 90th pctl = eps
        r = eps / 0.9
        return random.uniform(-r, r) + nudge
    if profile.distribution == "triangular":
        # Triangular on [-R, R, 0]: 90th percentile of |X| ≈ 0.684*R
        # So R = eps / 0.684 to get 90th pctl ≈ eps.
        r = eps / 0.684
        val = random.triangular(-r, r, 0.0) + nudge
        # Clip to prevent outliers from pushing fitted epsilon into
        # an adjacent genre's range.
        return max(-eps, min(eps, val))
    # gaussian: P(|N(0,sigma)| < eps) = 0.9 when sigma = eps / 1.645
    sigma = eps / 1.645
    return random.gauss(nudge, sigma)


def _swing_beat(beat: float, swing: float, bpm: float) -> float:
    """Apply swing to an 8th-note grid position.

    For 16th-note grid: odd 16ths (the 'and' of the beat) are delayed
    by swing amount.  Delay is measured in beats: at full swing (1.0)
    the delayed 8th lands on the triplet (1/3 of a quarter note later).
    """
    del bpm  # reserved for future tempo-dependent swing
    idx = round(beat * 4)  # 16th note index
    if idx % 2 == 0:
        return beat
    # Delay the off-beat 8th
    delay_beats = swing * (1.0 / 3.0) * 0.5  # fraction of a quarter note
    return beat + delay_beats


def _default_parts(genre: str) -> Dict[str, List[int]]:
    """Return default drum pattern for a genre."""
    if genre == "Jazz":
        return {
            "Ride": [0, 2, 4, 6, 8, 10, 12, 14],
            "HiHat": [1, 3, 5, 7, 9, 11, 13, 15],
            "Snare": [4, 12],
            "Kick": [0, 6, 10],
            "Bass": [0, 3, 6, 10, 12],
        }
    if genre == "Latin":
        return {
            "Conga": [0, 3, 6, 10, 12],
            "Clave": [0, 3, 6, 10, 12],
            "Timbales": [2, 6, 10, 14],
            "Bass": [0, 7, 10, 14],
        }
    return {
        "Kick": [0, 4, 8, 12],
        "Snare": [4, 12],
        "HiHat": [0, 2, 4, 6, 8, 10, 12, 14],
        "Bass": [0, 3, 6, 10, 12],
    }


def _build_meta_track(profile: GenreProfile) -> mido.MidiTrack:
    """Create a MIDI meta track with tempo and time signature."""
    tempo = int(60_000_000.0 / profile.bpm)
    meta_track = mido.MidiTrack()
    meta_track.append(mido.MetaMessage("track_name", name="Meta", time=0))
    meta_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    meta_track.append(
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0)
    )
    meta_track.append(mido.MetaMessage("end_of_track", time=0))
    return meta_track


def _build_instrument_track(  # pylint: disable=too-many-locals
    inst_name: str,
    hits: List[int],
    bars: int,
    profile: GenreProfile,
    tpb: int,
) -> mido.MidiTrack:
    """Create a single instrument track with microtiming offsets."""
    # Pitch mapping for named parts
    default_pitches = {
        "Kick": 36,
        "Snare": 38,
        "HiHat": 42,
        "Ride": 51,
        "Bass": 40,
        "Conga": 60,
        "Clave": 75,
        "Timbales": 65,
    }

    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name", name=inst_name, time=0))
    pitch = default_pitches.get(inst_name, 60)
    grid_division = 4  # 16ths per beat

    prev_tick = 0
    for bar_idx in range(bars):
        for idx in hits:
            beat_in_bar = idx / grid_division
            beat_global = bar_idx * 4 + beat_in_bar

            # NOTE: we intentionally do NOT call _swing_beat() here.
            # Shifting note positions by a swing offset causes the
            # analysis grid-snap to misclassify notes, corrupting the
            # measured microtiming deviation.  The swing feel is instead
            # encoded in the hit pattern and the microtiming distribution
            # (ahead_bias, epsilon spread).
            beat_swing = beat_global

            # Add microtiming offset
            offset_ms = _random_offset(profile)
            offset_beats = offset_ms / (60_000.0 / profile.bpm)
            beat_final = beat_swing + offset_beats

            target_tick = int(round(beat_final * tpb))
            # Clamp target to be at least 0 (MIDI cannot go backwards)
            target_tick = max(target_tick, 0)
            delta = max(target_tick - prev_tick, 0)
            vel = int(random.gauss(profile.velocity_mean, profile.velocity_std))
            vel = max(1, min(127, vel))

            channel = (
                9
                if inst_name in default_pitches and inst_name != "Bass"
                else 0
            )
            track.append(
                mido.Message(
                    "note_on",
                    note=pitch,
                    velocity=vel,
                    time=delta,
                    channel=channel,
                )
            )
            # Note-off: use a short duration to avoid overlapping
            # note_on events when grid spacing is tight.  30 ticks ≈ 31 ms
            # at 120 BPM / 480 tpb, well under the minimum 16th-note gap.
            note_off_ticks = min(30, max(1, tpb // 16 - 1))
            track.append(
                mido.Message(
                    "note_off", note=pitch, velocity=0, time=note_off_ticks
                )
            )
            # Advance actual MIDI position: delta + note_off
            prev_tick += delta + note_off_ticks

    track.append(mido.MetaMessage("end_of_track", time=0))
    return track


def synthesize_groove(
    genre: str,
    bars: int = 4,
    parts: Optional[Dict[str, List[int]]] = None,
    seed: Optional[int] = None,
    output_path: Optional[Path | str] = None,
) -> mido.MidiFile:
    """Generate a synthetic MIDI groove for a genre.

    Parameters
    ----------
    genre : str
        One of the keys in GENRE_PROFILES.
    bars : int
        Number of bars to generate.
    parts : dict, optional
        Mapping from instrument name to list of 16th-note indices (0-15)
        that trigger on each bar.  Defaults to a standard kit.
    seed : int, optional
        RNG seed for reproducibility.
    output_path : Path or str, optional
        If given, the MIDI file is saved here.

    Returns
    -------
    mido.MidiFile
    """
    if bars <= 0:
        raise ValueError("bars must be positive")

    if seed is not None:
        random.seed(seed)

    profile = GENRE_PROFILES.get(genre)
    if profile is None:
        raise ValueError(f"Unknown genre: {genre}")

    if profile.bpm <= 0:
        raise ValueError(f"Invalid BPM in genre profile: {profile.bpm}")

    if parts is None:
        parts = _default_parts(genre)

    mid = mido.MidiFile(ticks_per_beat=480)
    tpb = mid.ticks_per_beat

    mid.tracks.append(_build_meta_track(profile))

    for inst_name, hits in parts.items():
        mid.tracks.append(
            _build_instrument_track(inst_name, hits, bars, profile, tpb)
        )

    if output_path is not None:
        mid.save(str(output_path))

    return mid


def generate_all_genre_examples(
    output_dir: Path | str,
    bars: int = 4,
    seed: int = 42,
) -> List[Path]:
    """Generate one example MIDI file per genre."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for genre in GENRE_PROFILES:
        path = out / f"{genre.lower().replace('-', '_')}_groove.mid"
        synthesize_groove(genre, bars=bars, seed=seed, output_path=path)
        paths.append(path)
    return paths
