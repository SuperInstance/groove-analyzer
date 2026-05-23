"""Groove Analyzer — prove groove = deadband funnel."""

__version__ = "0.2.0"

from .exceptions import (
    GrooveAnalysisError,
    InvalidGrooveError,
)
from .microtiming import (
    extract_microtiming,
    GrooveTiming,
    TrackTiming,
    OnsetEvent,
    TimingClass,
)
from .deadband_groove import (
    fit_deadband,
    build_funnel,
    prove_groove_is_deadband,
    DeadbandFit,
    EnsembleFunnel,
    PlayerState,
)
from .genres import (
    GenreProfile,
    GENRE_PROFILES,
    synthesize_groove,
    generate_all_genre_examples,
)
from .visualize import (
    plot_deadband_funnel,
    plot_groove_comparison,
)

__all__ = [
    # Exceptions
    "GrooveAnalysisError",
    "InvalidGrooveError",
    # Microtiming
    "extract_microtiming",
    "GrooveTiming",
    "TrackTiming",
    "OnsetEvent",
    "TimingClass",
    # Deadband
    "fit_deadband",
    "build_funnel",
    "prove_groove_is_deadband",
    "DeadbandFit",
    "EnsembleFunnel",
    "PlayerState",
    # Genres
    "GenreProfile",
    "GENRE_PROFILES",
    "synthesize_groove",
    "generate_all_genre_examples",
    # Visualize
    "plot_deadband_funnel",
    "plot_groove_comparison",
]
