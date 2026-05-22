"""Extract microtiming features from MIDI files.

Given a MIDI file, we:
1. Parse note-on events per track / channel.
2. Convert absolute tick times to seconds via tempo map.
3. Quantize onsets to a regular grid (e.g. 16th notes).
4. Measure the deviation of each onset from its nearest grid line.
5. Compute summary statistics per instrument / global.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import mido


class TimingClass(str, Enum):
    AHEAD = "ahead"      # early, pushing the beat
    BEHIND = "behind"    # late, laying back
    POCKET = "pocket"    # within the groove pocket


@dataclass
class OnsetEvent:  # pylint: disable=too-many-instance-attributes
    """A single note onset with its timing data."""
    time_sec: float       # absolute time in seconds
    beat: float           # absolute position in beats
    pitch: int
    velocity: int
    channel: int
    track_name: str
    grid_line: float      # nearest grid line in beats
    deviation_ms: float   # deviation from grid in ms (+ = behind, - = ahead)
    timing_class: TimingClass = TimingClass.POCKET

    def __post_init__(self) -> None:
        if not isinstance(self.time_sec, (int, float)):
            raise TypeError(
                f"time_sec must be a number, got {type(self.time_sec).__name__}"
            )
        if isinstance(self.time_sec, float) and (
            math.isnan(self.time_sec) or math.isinf(self.time_sec)
        ):
            raise ValueError(f"time_sec must be finite, got {self.time_sec}")

    def __repr__(self) -> str:
        return (
            f"OnsetEvent(beat={self.beat:.3f}, dev={self.deviation_ms:.2f}ms, "
            f"pitch={self.pitch}, track={self.track_name!r})"
        )


@dataclass
class TrackTiming:  # pylint: disable=too-many-instance-attributes
    """Timing summary for one track / instrument."""
    track_name: str
    onsets: List[OnsetEvent] = field(default_factory=list)
    avg_offset_ms: float = 0.0
    std_offset_ms: float = 0.0
    swing_factor: float = 0.0
    pocket_width_ms: float = 0.0
    ahead_pct: float = 0.0
    behind_pct: float = 0.0
    pocket_pct: float = 0.0

    def __repr__(self) -> str:
        return (
            f"TrackTiming(name={self.track_name!r}, onsets={len(self.onsets)}, "
            f"avg={self.avg_offset_ms:.2f}ms, std={self.std_offset_ms:.2f}ms)"
        )


@dataclass
class GrooveTiming:  # pylint: disable=too-many-instance-attributes
    """Complete timing analysis for a MIDI file."""
    bpm: float
    ticks_per_beat: int
    grid_division: int
    tracks: List[TrackTiming] = field(default_factory=list)
    global_avg_offset_ms: float = 0.0
    global_std_offset_ms: float = 0.0
    global_pocket_width_ms: float = 0.0
    global_swing_factor: float = 0.0

    def __repr__(self) -> str:
        return (
            f"GrooveTiming(bpm={self.bpm:.1f}, tracks={len(self.tracks)}, "
            f"grid={self.grid_division})"
        )


def _build_tempo_map(mid: mido.MidiFile) -> List[Tuple[int, int]]:
    """Return list of (absolute_tick, tempo_microseconds) from track 0."""
    tempos: List[Tuple[int, int]] = []
    tick = 0
    for msg in mid.tracks[0]:
        tick += msg.time
        if msg.type == "set_tempo":
            tempos.append((tick, msg.tempo))
    if not tempos:
        tempos.append((0, 500_000))  # default 120 BPM
    return tempos


def _tick_to_seconds(
    tick: int,
    tempo_map: List[Tuple[int, int]],
    ticks_per_beat: int,
) -> float:
    """Convert absolute tick count to seconds using the tempo map."""
    sec = 0.0
    prev_tick = 0
    prev_tempo = tempo_map[0][1]
    for map_tick, tempo in tempo_map:
        if tick < map_tick:
            break
        sec += (map_tick - prev_tick) * (prev_tempo / 1_000_000.0) / ticks_per_beat
        prev_tick = map_tick
        prev_tempo = tempo
    sec += (tick - prev_tick) * (prev_tempo / 1_000_000.0) / ticks_per_beat
    return sec


def _snap_to_grid(beat: float, division: int) -> float:
    """Return nearest grid line in beats for a given division."""
    return round(beat * division) / division


def _classify_deviation(deviation_ms: float, pocket_ms: float) -> TimingClass:
    if abs(deviation_ms) <= pocket_ms:
        return TimingClass.POCKET
    return TimingClass.BEHIND if deviation_ms > 0 else TimingClass.AHEAD


def _compute_swing(onsets: List[OnsetEvent], grid_division: int) -> float:
    """Estimate swing factor from 8th-note triplet feel.

    Swing is measured as the ratio between the long and short 8th-note
    divisions when grid is 16th notes.  A value of 0.0 means even 8ths;
    1.0 means full triplet swing.
    """
    if grid_division < 4:
        return 0.0

    # Collect deviations on odd 16th notes (the "ands" of the beat)
    # In 16th-note grid: beat positions 0, 0.25, 0.5, 0.75, ...
    # Odd indices = 0.25, 0.75, ...
    odd_devs: List[float] = []
    even_devs: List[float] = []
    for o in onsets:
        idx = round(o.beat * grid_division)
        if idx % 2 == 0:
            even_devs.append(o.deviation_ms)
        else:
            odd_devs.append(o.deviation_ms)

    if not odd_devs or not even_devs:
        return 0.0

    # Swing factor: difference in average lateness between odd and even 16ths,
    # normalised by a heuristic max of 40 ms.
    diff = sum(odd_devs) / len(odd_devs) - sum(even_devs) / len(even_devs)
    return max(0.0, min(1.0, diff / 40.0))


def _gather_track_events(
    mid: mido.MidiFile,
) -> Dict[int, List[Tuple[int, int, int, int, str]]]:
    """Collect note-on events per track from a MIDI file."""
    track_events: Dict[int, List[Tuple[int, int, int, int, str]]] = {}
    for track_idx, track in enumerate(mid.tracks):
        name = f"track_{track_idx}"
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == "track_name":
                name = msg.name or name
            elif msg.type == "note_on" and msg.velocity > 0:
                track_events.setdefault(track_idx, []).append(
                    (tick, msg.note, msg.velocity, msg.channel, name)
                )
    return track_events


def _make_onsets(
    events: List[Tuple[int, int, int, int, str]],
    tempo_map: List[Tuple[int, int]],
    ticks_per_beat: int,
    grid_division: int,
    bpm: float,
) -> List[OnsetEvent]:
    """Create OnsetEvent list from raw MIDI events."""
    name = events[0][4]
    onsets: List[OnsetEvent] = []
    for tick, pitch, velocity, channel, _ in events:
        sec = _tick_to_seconds(tick, tempo_map, ticks_per_beat)
        beat = tick / ticks_per_beat
        grid = _snap_to_grid(beat, grid_division)
        deviation = (beat - grid) * (60_000.0 / bpm)
        onsets.append(OnsetEvent(
            time_sec=sec,
            beat=beat,
            pitch=pitch,
            velocity=velocity,
            channel=channel,
            track_name=name,
            grid_line=grid,
            deviation_ms=deviation,
        ))
    onsets.sort(key=lambda o: o.time_sec)
    return onsets


def _compute_pocket_threshold(deviations: List[float]) -> float:
    """Compute pocket threshold from deviations using MAD."""
    med = float(sorted(deviations)[len(deviations) // 2])
    mad = float(
        sorted(abs(d - med) for d in deviations)[len(deviations) // 2]
    )
    return 1.5 * mad if mad > 0 else 10.0


def _track_statistics(
    onsets: List[OnsetEvent],
    grid_division: int,
) -> Tuple[float, float, float, float, float, float]:
    """Return (avg, std, swing, ahead_pct, behind_pct, pocket_pct)."""
    deviations = [o.deviation_ms for o in onsets]
    avg = sum(deviations) / len(deviations) if deviations else 0.0
    std = (
        math.sqrt(sum((d - avg) ** 2 for d in deviations) / len(deviations))
        if deviations else 0.0
    )
    swing = _compute_swing(onsets, grid_division)

    n_total = len(onsets)
    n_ahead = sum(1 for o in onsets if o.timing_class == TimingClass.AHEAD)
    n_behind = sum(1 for o in onsets if o.timing_class == TimingClass.BEHIND)
    n_pocket = sum(1 for o in onsets if o.timing_class == TimingClass.POCKET)

    ahead_pct = 100.0 * n_ahead / n_total if n_total else 0.0
    behind_pct = 100.0 * n_behind / n_total if n_total else 0.0
    pocket_pct = 100.0 * n_pocket / n_total if n_total else 0.0

    return avg, std, swing, ahead_pct, behind_pct, pocket_pct


def _analyse_track(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    events: List[Tuple[int, int, int, int, str]],
    tempo_map: List[Tuple[int, int]],
    ticks_per_beat: int,
    grid_division: int,
    bpm: float,
    pocket_ms: Optional[float],
) -> TrackTiming:
    """Build a TrackTiming from raw note-on events."""
    onsets = _make_onsets(events, tempo_map, ticks_per_beat, grid_division, bpm)

    # Pocket threshold
    if pocket_ms is None:
        threshold = _compute_pocket_threshold([o.deviation_ms for o in onsets])
    else:
        threshold = pocket_ms

    # Classify each onset
    for o in onsets:
        o.timing_class = _classify_deviation(o.deviation_ms, threshold)

    avg, std, swing, ahead_pct, behind_pct, pocket_pct = _track_statistics(
        onsets, grid_division
    )

    return TrackTiming(
        track_name=events[0][4],
        onsets=onsets,
        avg_offset_ms=avg,
        std_offset_ms=std,
        swing_factor=swing,
        pocket_width_ms=threshold,
        ahead_pct=ahead_pct,
        behind_pct=behind_pct,
        pocket_pct=pocket_pct,
    )


def _global_stats(
    all_onsets: List[OnsetEvent],
    grid_division: int,
) -> Tuple[float, float, float, float]:
    """Return (avg, std, pocket, swing) for all onsets."""
    if not all_onsets:
        return 0.0, 0.0, 0.0, 0.0

    g_devs = [o.deviation_ms for o in all_onsets]
    g_avg = sum(g_devs) / len(g_devs)
    g_std = math.sqrt(
        sum((d - g_avg) ** 2 for d in g_devs) / len(g_devs)
    )
    g_med = float(sorted(g_devs)[len(g_devs) // 2])
    g_mad = float(
        sorted(abs(d - g_med) for d in g_devs)[len(g_devs) // 2]
    )
    g_pocket = 1.5 * g_mad if g_mad > 0 else 10.0
    g_swing = _compute_swing(all_onsets, grid_division)
    return g_avg, g_std, g_pocket, g_swing


def _build_tracks(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    track_events: Dict[int, List[Tuple[int, int, int, int, str]]],
    tempo_map: List[Tuple[int, int]],
    tpb: int,
    grid_division: int,
    bpm: float,
    pocket_ms: Optional[float],
) -> Tuple[List[TrackTiming], List[OnsetEvent]]:
    """Analyse all tracks and return (tracks, all_onsets)."""
    tracks: List[TrackTiming] = []
    all_onsets: List[OnsetEvent] = []
    for events in track_events.values():
        if not events:
            continue
        tt = _analyse_track(events, tempo_map, tpb, grid_division, bpm, pocket_ms)
        tracks.append(tt)
        all_onsets.extend(tt.onsets)
    return tracks, all_onsets


def extract_microtiming(
    path: Path | str,
    grid_division: int = 4,
    pocket_ms: Optional[float] = None,
) -> GrooveTiming:
    """Analyse microtiming in a MIDI file.

    Parameters
    ----------
    path : Path or str
        Path to the MIDI file.
    grid_division : int
        Grid resolution in parts per beat (4 = quarter, 8 = 8th, 16 = 16th).
    pocket_ms : float, optional
        Threshold in ms for the "pocket" classification.  If None, computed
        from the data as 1.5 x median absolute deviation.

    Returns
    -------
    GrooveTiming
    """
    if grid_division <= 0:
        raise ValueError("grid_division must be positive")

    mid = mido.MidiFile(str(path))

    if not mid.tracks:
        raise ValueError(
            f"MIDI file '{path}' contains no tracks — nothing to analyse."
        )

    tpb = mid.ticks_per_beat
    tempo_map = _build_tempo_map(mid)
    bpm = 60_000_000.0 / tempo_map[0][1]

    track_events = _gather_track_events(mid)

    if not track_events:
        import warnings
        warnings.warn(
            f"MIDI file '{path}' contains no note_on events — "
            "returning empty GrooveTiming.",
            stacklevel=2,
        )
        return GrooveTiming(
            bpm=bpm,
            ticks_per_beat=tpb,
            grid_division=grid_division,
            tracks=[],
            global_avg_offset_ms=0.0,
            global_std_offset_ms=0.0,
            global_pocket_width_ms=0.0,
            global_swing_factor=0.0,
        )

    tracks, all_onsets = _build_tracks(
        track_events, tempo_map, tpb, grid_division, bpm, pocket_ms
    )

    g_avg, g_std, g_pocket, g_swing = _global_stats(all_onsets, grid_division)

    return GrooveTiming(
        bpm=bpm,
        ticks_per_beat=tpb,
        grid_division=grid_division,
        tracks=tracks,
        global_avg_offset_ms=g_avg,
        global_std_offset_ms=g_std,
        global_pocket_width_ms=g_pocket,
        global_swing_factor=g_swing,
    )
