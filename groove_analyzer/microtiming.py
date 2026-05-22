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
class OnsetEvent:
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


@dataclass
class TrackTiming:
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


@dataclass
class GrooveTiming:
    """Complete timing analysis for a MIDI file."""
    bpm: float
    ticks_per_beat: int
    grid_division: int
    tracks: List[TrackTiming] = field(default_factory=list)
    global_avg_offset_ms: float = 0.0
    global_std_offset_ms: float = 0.0
    global_pocket_width_ms: float = 0.0
    global_swing_factor: float = 0.0


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


def _tick_to_seconds(tick: int, tempo_map: List[Tuple[int, int]], ticks_per_beat: int) -> float:
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


def extract_microtiming(
    path: Path | str,
    grid_division: int = 16,
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
        from the data as 1.5 × median absolute deviation.

    Returns
    -------
    GrooveTiming
    """
    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat
    tempo_map = _build_tempo_map(mid)
    default_tempo = tempo_map[0][1]
    bpm = 60_000_000.0 / default_tempo

    # Gather note-on events per track
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

    all_onsets: List[OnsetEvent] = []
    tracks: List[TrackTiming] = []

    for track_idx, events in track_events.items():
        if not events:
            continue
        name = events[0][4]
        onsets: List[OnsetEvent] = []
        for tick, pitch, velocity, channel, _ in events:
            sec = _tick_to_seconds(tick, tempo_map, tpb)
            beat = tick / tpb
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

        # Sort by time
        onsets.sort(key=lambda o: o.time_sec)

        # Global pocket threshold if not provided
        if pocket_ms is None:
            deviations = [o.deviation_ms for o in onsets]
            med = float(sorted(deviations)[len(deviations) // 2])
            mad = float(sorted(abs(d - med) for d in deviations)[len(deviations) // 2])
            threshold = 1.5 * mad if mad > 0 else 10.0
        else:
            threshold = pocket_ms

        # Classify each onset
        for o in onsets:
            o.timing_class = _classify_deviation(o.deviation_ms, threshold)

        deviations = [o.deviation_ms for o in onsets]
        avg = sum(deviations) / len(deviations) if deviations else 0.0
        std = math.sqrt(sum((d - avg) ** 2 for d in deviations) / len(deviations)) if deviations else 0.0
        swing = _compute_swing(onsets, grid_division)

        n_total = len(onsets)
        n_ahead = sum(1 for o in onsets if o.timing_class == TimingClass.AHEAD)
        n_behind = sum(1 for o in onsets if o.timing_class == TimingClass.BEHIND)
        n_pocket = sum(1 for o in onsets if o.timing_class == TimingClass.POCKET)

        tt = TrackTiming(
            track_name=name,
            onsets=onsets,
            avg_offset_ms=avg,
            std_offset_ms=std,
            swing_factor=swing,
            pocket_width_ms=threshold,
            ahead_pct=100.0 * n_ahead / n_total if n_total else 0.0,
            behind_pct=100.0 * n_behind / n_total if n_total else 0.0,
            pocket_pct=100.0 * n_pocket / n_total if n_total else 0.0,
        )
        tracks.append(tt)
        all_onsets.extend(onsets)

    # Global stats
    if all_onsets:
        g_devs = [o.deviation_ms for o in all_onsets]
        g_avg = sum(g_devs) / len(g_devs)
        g_std = math.sqrt(sum((d - g_avg) ** 2 for d in g_devs) / len(g_devs))
        g_med = float(sorted(g_devs)[len(g_devs) // 2])
        g_mad = float(sorted(abs(d - g_med) for d in g_devs)[len(g_devs) // 2])
        g_pocket = 1.5 * g_mad if g_mad > 0 else 10.0
        g_swing = _compute_swing(all_onsets, grid_division)
    else:
        g_avg = g_std = g_pocket = g_swing = 0.0

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
