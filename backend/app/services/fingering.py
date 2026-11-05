"""Choose a playable string/fret for every detected note (Viterbi over all positions).

The same pitch can be played on several strings. We pick the sequence that minimises
how far and how often the fretting hand moves, the way a bassist would:
- staying inside a 4-fret "box" is cheap; shifting the hand costs more the further it goes
- open strings need no fretting finger (cheap, hand stays put)
- string skips cost a little; very high frets cost a little
- a long pause before a note makes a position shift cheaper (time to move)
- repeated identical pitches strongly prefer the same position
Works for any tuning (4/5/6 strings, drop, custom). string 1 = highest string.
"""
from dataclasses import dataclass

from .music import note_to_midi

MAX_FRET = 24
COMFORT_FRET = 12


@dataclass
class Placed:
    string: int
    fret: int
    transposed: int = 0  # octaves shifted to fit the instrument (flag for review)


def open_midis(tuning: list[str]) -> list[int]:
    """Open-string MIDI per string number (index 0 -> string 1 = highest)."""
    return [note_to_midi(n) for n in reversed(tuning)]


def candidates(midi: int, opens: list[int], max_fret: int = MAX_FRET) -> list[tuple[int, int]]:
    return [(i + 1, midi - o) for i, o in enumerate(opens) if 0 <= midi - o <= max_fret]


def _pos_cost(fret: int) -> float:
    return 0.08 * max(0, fret - COMFORT_FRET)


def _move_cost(a: tuple[int, int], b: tuple[int, int], dt: float, same_pitch: bool) -> float:
    (s1, f1), (s2, f2) = a, b
    if same_pitch:
        return 0.0 if a == b else 1.5
    cost = 0.25 * max(0, abs(s2 - s1) - 1)  # skipping strings
    if f1 == 0 or f2 == 0:
        cost += 0.3  # open string: no shift needed, small coordination cost
    else:
        d = abs(f2 - f1)
        shift = 0.15 * d if d <= 3 else 1.0 + 0.5 * (d - 3)
        if dt > 0.8:  # enough time to move the hand
            shift *= 0.4
        cost += shift
    return cost


def assign(notes: list[tuple[float, float, int]], tuning: list[str], max_fret: int = MAX_FRET) -> list[Placed]:
    """notes: (start_time, duration, midi) sorted by time. Returns one Placed per note."""
    opens = open_midis(tuning)
    lo, hi = min(opens), max(opens) + max_fret
    fitted: list[tuple[int, int]] = []  # (midi_used, octave_shift)
    for _, _, m in notes:
        shift = 0
        while m + 12 * shift < lo:
            shift += 1
        while m + 12 * shift > hi:
            shift -= 1
        fitted.append((m + 12 * shift, shift))
    if not notes:
        return []

    cands = [candidates(m, opens, max_fret) for m, _ in fitted]
    # Viterbi
    cost = [[_pos_cost(f) for _, f in cands[0]]]
    back: list[list[int]] = [[-1] * len(cands[0])]
    for i in range(1, len(notes)):
        prev_end = notes[i - 1][0] + notes[i - 1][1]
        dt = max(0.0, notes[i][0] - prev_end)
        same = fitted[i][0] == fitted[i - 1][0]
        row, brow = [], []
        for c in cands[i]:
            best, arg = float("inf"), 0
            for j, p in enumerate(cands[i - 1]):
                v = cost[i - 1][j] + _move_cost(p, c, dt, same)
                if v < best:
                    best, arg = v, j
            row.append(best + _pos_cost(c[1]))
            brow.append(arg)
        cost.append(row)
        back.append(brow)
    k = min(range(len(cost[-1])), key=cost[-1].__getitem__)
    path = []
    for i in range(len(notes) - 1, -1, -1):
        s, f = cands[i][k]
        path.append(Placed(s, f, fitted[i][1]))
        k = back[i][k]
    return path[::-1]
