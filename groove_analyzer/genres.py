"""Genre-specific deadband profiles and synthetic groove generation.

Each genre is characterised by a deadband ε, a swing factor, and a
statistical distribution of microtiming offsets.  We synthesise grooves
by placing notes on a metronome grid and then perturbing each onset by
a random offset drawn from the genre's deadband distribution.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import mido


@dataclass
class GenreProfile:
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
    """Draw a microtiming offset in ms from the genre's distribution."""
    low, high = profile.epsilon_range
    if profile.distribution == "uniform":
        return random.uniform(low, high) * random.choice((-1, 1)) + profile.ahead_bias
    elif profile.distribution == "triangular":
        # Triangular centred on bias, width = epsilon_range
        mode = profile.ahead_bias
        return random.triangular(low - abs(mode), high + abs(mode), mode)
    else:  # gaussian
        sigma = (high - low) / 4.0
        return random.gauss(profile.ahead_bias, sigma)


def _swing_beat(beat: float, swing: float, bpm: float) -> float:
    """Apply swing to an 8th-note grid position.

    For 16th-note grid: odd 16ths (the 'and' of the beat) are delayed
    by swing amount.  Delay is measured in beats: at full swing (1.0)
    the delayed 8th lands on the triplet (1/3 of a quarter note later).
    """
    idx = round(beat * 4)  # 16th note index
    if idx % 2 == 0:
        return beat
    # Delay the off-beat 8th
    delay_beats = swing * (1.0 / 3.0) * 0.5  # fraction of a quarter note
    return beat + delay_beats


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
    if seed is not None:
        random.seed(seed)

    profile = GENRE_PROFILES.get(genre)
    if profile is None:
        raise ValueError(f"Unknown genre: {genre}")

    if parts is None:
        # Standard drum-kit pattern (16th-note indices per bar)
        if genre == "Jazz":
            parts = {
                "Ride": [0, 2, 4, 6, 8, 10, 12, 14],
                "HiHat": [1, 3, 5, 7, 9, 11, 13, 15],
                "Snare": [4, 12],
                "Kick": [0, 6, 10],
                "Bass": [0, 3, 6, 10, 12],
            }
        elif genre == "Latin":
            parts = {
                "Conga": [0, 3, 6, 10, 12],
                "Clave": [0, 3, 6, 10, 12],
                "Timbales": [2, 6, 10, 14],
                "Bass": [0, 7, 10, 14],
            }
        else:
            parts = {
                "Kick": [0, 4, 8, 12],
                "Snare": [4, 12],
                "HiHat": [0, 2, 4, 6, 8, 10, 12, 14],
                "Bass": [0, 3, 6, 10, 12],
            }

    mid = mido.MidiFile(ticks_per_beat=480)
    tpb = mid.ticks_per_beat
    tempo = int(60_000_000.0 / profile.bpm)
    grid_division = 4  # 16ths per beat
    tick_per_16th = tpb // grid_division

    # Track 0: tempo + time sig
    meta_track = mido.MidiTrack()
    meta_track.append(mido.MetaMessage("track_name", name="Meta", time=0))
    meta_track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    meta_track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    meta_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(meta_track)

    # Pitch mapping for named parts
    default_pitches = {
        "Kick": 36, "Snare": 38, "HiHat": 42, "Ride": 51,
        "Bass": 40, "Conga": 60, "Clave": 75, "Timbales": 65,
    }

    for inst_name, hits in parts.items():
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=inst_name, time=0))
        pitch = default_pitches.get(inst_name, 60)

        prev_tick = 0
        for bar in range(bars):
            for idx in hits:
                beat_in_bar = idx / grid_division
                beat_global = bar * 4 + beat_in_bar
                beat_swing = _swing_beat(beat_global, profile.swing_factor, profile.bpm)

                # Add microtiming offset
                offset_ms = _random_offset(profile)
                offset_beats = offset_ms / (60_000.0 / profile.bpm)
                beat_final = beat_swing + offset_beats

                tick = int(round(beat_final * tpb))
                delta = tick - prev_tick
                if delta < 0:
                    delta = 0
                vel = int(random.gauss(profile.velocity_mean, profile.velocity_std))
                vel = max(1, min(127, vel))

                track.append(mido.Message("note_on", note=pitch, velocity=vel, time=delta, channel=9 if inst_name in default_pitches and inst_name != "Bass" else 0))
                # Note-off 100 ticks later (on same track, correct delta handling would be more complex)
                # For simplicity, we insert note_off with delta 0 right after
                track.append(mido.Message("note_off", note=pitch, velocity=0, time=100))
                prev_tick = tick + 100

        track.append(mido.MetaMessage("end_of_track", time=0))
        mid.tracks.append(track)

    if output_path is not None:
        mid.save(str(output_path))

    return mid


def generate_all_genre_examples(output_dir: Path | str, bars: int = 4, seed: int = 42) -> List[Path]:
    """Generate one example MIDI file per genre."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for genre in GENRE_PROFILES:
        path = out / f"{genre.lower().replace('-', '_')}_groove.mid"
        synthesize_groove(genre, bars=bars, seed=seed, output_path=path)
        paths.append(path)
    return paths
