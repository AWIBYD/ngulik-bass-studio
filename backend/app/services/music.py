"""Pitch / tuning helpers. MIDI note numbers, A4 = 69 = 440 Hz."""
import re

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d)$")

PRESET_TUNINGS: dict[str, list[str]] = {
    "4-string standard (E-A-D-G)": ["E1", "A1", "D2", "G2"],
    "5-string standard (B-E-A-D-G)": ["B0", "E1", "A1", "D2", "G2"],
    "6-string standard (B-E-A-D-G-C)": ["B0", "E1", "A1", "D2", "G2", "C3"],
    "4-string drop D (D-A-D-G)": ["D1", "A1", "D2", "G2"],
}

MAX_FRET = 24


def note_to_midi(name: str) -> int:
    m = _RE.match(name.strip())
    if not m:
        raise ValueError(f"Invalid note name: {name!r}")
    letter, acc, octave = m.group(1).upper(), m.group(2), int(m.group(3))
    pc = letter + acc
    pc = _FLATS.get(pc, pc)
    if pc not in NOTE_NAMES:  # e.g. "E#", "Cb"
        raise ValueError(f"Invalid note name: {name!r}")
    return (octave + 1) * 12 + NOTE_NAMES.index(pc)


def midi_to_note(midi: int) -> str:
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def midi_to_freq(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def validate_tuning(tuning: list[str]) -> list[str]:
    if not 4 <= len(tuning) <= 6:
        raise ValueError("Tuning must have 4 to 6 strings")
    midis = [note_to_midi(n) for n in tuning]
    if any(m < 12 or m > 72 for m in midis):
        raise ValueError("Tuning notes out of bass range")
    return [midi_to_note(m) for m in midis]


def string_open_midi(tuning: list[str], string_number: int) -> int:
    """string_number 1 = highest-pitched string (top line of a tab)."""
    n = len(tuning)
    if not 1 <= string_number <= n:
        raise ValueError("string_number out of range")
    return note_to_midi(tuning[n - string_number])
