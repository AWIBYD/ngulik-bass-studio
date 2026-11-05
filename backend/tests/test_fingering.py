from app.services.fingering import assign, candidates, open_midis
from app.services.music import note_to_midi

STD4 = ["E1", "A1", "D2", "G2"]
STD5 = ["B0", "E1", "A1", "D2", "G2"]


def seq(names, step=0.25):
    return [(i * step, step * 0.9, note_to_midi(n)) for i, n in enumerate(names)]


def test_candidates_cover_all_strings():
    assert candidates(note_to_midi("A1"), open_midis(STD4)) == [(3, 0), (4, 5)]


def test_stays_in_one_box_for_a_scale():
    # G major scale from G1 in 2nd... a typical one-position fingering around fret 3
    placed = assign(seq(["G1", "A1", "B1", "C2", "D2", "E2", "F#2", "G2"]), STD4)
    frets = [p.fret for p in placed if p.fret]
    assert max(frets) - min(frets) <= 4, placed


def test_repeated_notes_keep_position():
    placed = assign(seq(["A1"] * 6 + ["D2"] * 4), STD4)
    assert len({(p.string, p.fret) for p in placed[:6]}) == 1
    assert len({(p.string, p.fret) for p in placed[6:]}) == 1


def test_low_b_uses_five_string_and_transposes_on_four():
    assert assign(seq(["B0"]), STD5)[0].fret == 0 and assign(seq(["B0"]), STD5)[0].string == 5
    p = assign(seq(["B0"]), STD4)[0]
    assert p.transposed == 1  # flagged: octave up to fit a 4-string


def test_high_riff_moves_up_neck_instead_of_jumping():
    placed = assign(seq(["C3", "D3", "E3", "D3", "C3"]), STD4)
    assert all(p.string == 1 for p in placed)  # stays on G string in high position
    assert all(5 <= p.fret <= 9 for p in placed)


def test_drop_d_low_d_is_open():
    p = assign(seq(["D1"]), ["D1", "A1", "D2", "G2"])[0]
    assert (p.string, p.fret) == (4, 0)


def test_empty():
    assert assign([], STD4) == []
