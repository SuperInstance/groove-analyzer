"""Custom exceptions for groove-analyzer."""


class GrooveAnalysisError(Exception):
    """Base exception for all groove analysis errors."""

    def __init__(self, message: str, *, path: str | None = None) -> None:
        self.path = path
        super().__init__(message)


class InvalidGrooveError(GrooveAnalysisError):
    """Raised when groove data is invalid or cannot be analysed.

    This covers cases such as:
    - Empty MIDI files with no note events
    - Invalid BPM values
    - Corrupt or unreadable MIDI data
    """
